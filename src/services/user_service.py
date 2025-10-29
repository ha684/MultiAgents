# src/services/user_service.py

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import uuid
from zoneinfo import ZoneInfo

from sqlalchemy import and_, delete, func, update
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from src.core.config.settings import ROLE_PERMISSIONS, settings
from src.core.exceptions.auth_exceptions import (
    DatabaseException,
    UserAlreadyExistsException,
    UserNotFoundException,
)
from src.core.security import PasswordManager, TokenManager
from src.database.models.user import (
    LoginAttempt,
    Permission,
    RefreshToken,
    User,
    UserPermission,
    UserRole,
    UserStatus,
)
from src.dependencies.database_session import DatabaseSession
from src.domain.schemas.auth import UserRegistrationRequest
from src.infrastructure.cache import redis_client
from src.services.utils import send_verification_email
from src.utils.decorators import singleton
from src.utils.logger_conf import logger


USER_BY_ID = "user:by_id"
USER_BY_EMAIL = "user:by_email"


@singleton
class UserRepository:
    """User database operations"""

    async def create_user(self, user_data: UserRegistrationRequest) -> User:
        """Create a new user"""
        try:
            hashed_password = PasswordManager.hash_password(user_data.password)
            verification_token, verification_expires = (
                TokenManager.create_verification_token()
            )

            new_user = User(
                email=user_data.email,
                username=user_data.username,
                full_name=user_data.full_name,
                hashed_password=hashed_password,
                role=UserRole.USER,
                status=UserStatus.PENDING_VERIFICATION,
                email_verification_token=verification_token,
                email_verification_expires=verification_expires,
                created_at=datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")),
                updated_at=datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")),
            )

            async with DatabaseSession() as session:
                session.add(new_user)
                await session.flush()
                await session.refresh(new_user)
                await send_verification_email(new_user)

            await self.assign_default_permissions(new_user.id)

            return new_user

        except Exception as e:
            logger.error("Error creating user")
            if isinstance(e, UserAlreadyExistsException):
                raise
            raise DatabaseException("Failed to create user")

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        email_l = email.lower().strip()

        cached = await redis_client.get_obj(USER_BY_EMAIL, email_l)
        if cached:
            return _user_from_cache(cached)

        lock_key = f"lock:user:email:{email_l}"
        locked = await redis_client.get().set(lock_key, "1", nx=True, ex=5)

        if locked:
            try:
                async with DatabaseSession() as session:
                    result = await session.execute(
                        select(User).where(User.email == email_l)
                    )
                    user = result.scalar_one_or_none()
                    if user:
                        await redis_client.set_obj(
                            USER_BY_EMAIL, _user_to_cache(user), email_l
                        )
                        await redis_client.set_obj(
                            USER_BY_ID, _user_to_cache(user), str(user.id)
                        )
                    return user

            except Exception as e:
                logger.error(f"Error getting user by email: {str(e)}")
                raise DatabaseException("Failed to retrieve user")
            finally:
                await redis_client.get().delete(lock_key)
        else:
            await asyncio.sleep(0.05)
            return await self.get_user_by_email(email)

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID"""
        uid = str(user_id)

        cached = await redis_client.get_obj(USER_BY_ID, uid)
        if cached:
            return _user_from_cache(cached)

        lock_key = f"lock:user:id:{uid}"
        locked = await redis_client.get().set(lock_key, "1", nx=True, ex=5)

        if locked:
            try:
                async with DatabaseSession() as session:
                    result = await session.execute(
                        select(User).where(User.id == uuid.UUID(user_id))
                    )
                    user = result.scalar_one_or_none()
                    if user:
                        await redis_client.set_obj(
                            USER_BY_ID, _user_to_cache(user), uid
                        )
                        return user
            except Exception as e:
                logger.error(f"Error getting user by ID: {str(e)}")
                raise DatabaseException("Failed to retrieve user")
            finally:
                await redis_client.get().delete(lock_key)
        else:
            await asyncio.sleep(0.05)
            return await self.get_user_by_id(user_id)

    async def get_user_with_permissions(self, user_id: str) -> Optional[User]:
        """Get user with their permissions"""
        try:
            async with DatabaseSession() as session:
                result = await session.execute(
                    select(User)
                    .options(
                        selectinload(User.user_permissions).selectinload(
                            UserPermission.permission
                        )
                    )
                    .where(User.id == uuid.UUID(user_id))
                )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting user with permissions: {str(e)}")
            raise DatabaseException("Failed to retrieve user with permissions")

    async def update_user(self, user_id: str, update_data: Dict[str, Any]) -> User:
        """Update user information"""
        try:
            async with DatabaseSession() as session:
                stmt = select(User).where(User.id == uuid.UUID(user_id))
                result = await session.execute(stmt)
                await session.commit()

                user = result.scalar_one_or_none()
                if not user:
                    raise UserNotFoundException()

                old_email = user.email.lower().strip()
                new_email = update_data.get("email", old_email).lower()

                for field, value in update_data.items():
                    if hasattr(user, field):
                        setattr(user, field, value)

                user.updated_at = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
                await session.commit()
                await session.refresh(user)
                await _invalidate_user_cache(
                    user, old_email if old_email != new_email else None
                )

            return user
        except Exception as e:
            logger.error(f"Error updating user: {str(e)}")
            if isinstance(e, UserNotFoundException):
                raise
            raise DatabaseException("Failed to update user")

    async def delete_user(self, user_id: str) -> bool:
        """Delete a user"""
        try:
            async with DatabaseSession() as session:
                result = await session.execute(
                    delete(User).where(User.id == uuid.UUID(user_id))
                )
                user_to_delete = result.scalar_one_or_none()
                if user_to_delete:
                    await _invalidate_user_cache(user_to_delete)
                    return True
                return False
        except Exception as e:
            logger.error(f"Error deleting user: {str(e)}")
            raise DatabaseException("Failed to delete user")

    async def verify_email(self, token: str) -> Optional[User]:
        """Verify user email with token"""
        try:
            async with DatabaseSession() as session:
                result = await session.execute(
                    select(User).where(
                        and_(
                            User.email_verification_token == token,
                            User.email_verification_expires
                            > datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")),
                            User.status == UserStatus.PENDING_VERIFICATION,
                        )
                    )
                )
                user = result.scalar_one_or_none()

                if user:
                    user.email_verified = True
                    user.status = UserStatus.ACTIVE
                    user.email_verification_token = None
                    user.email_verification_expires = None
                    user.updated_at = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
                    await session.flush()
                    await _invalidate_user_cache(user)
            return user
        except Exception as e:
            logger.error(f"Error verifying email: {str(e)}")
            raise DatabaseException("Failed to verify email")

    async def update_last_login(self, user_id: str) -> None:
        """Update user's last login timestamp AND invalidate cache"""
        try:
            async with DatabaseSession() as session:
                stmt = (
                    update(User)
                    .where(User.id == uuid.UUID(user_id))
                    .values(last_login_at=datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")))
                    .returning(User)
                )

                result = await session.execute(stmt)
                await session.commit()

                user = result.scalar_one_or_none()

                if user:
                    await _invalidate_user_cache(user)

        except Exception as e:
            logger.error(f"Error updating last login: {str(e)}")
            raise DatabaseException("Failed to update last login")

    async def increment_failed_login_attempts(self, email: str) -> User:
        """Increment failed login attempts and potentially lock account"""
        try:
            user = await self.get_user_by_email(email)
            if not user:
                return None

            user.failed_login_attempts += 1

            if user.failed_login_attempts >= settings.max_login_attempts:
                user.account_locked_until = datetime.now(
                    ZoneInfo("Asia/Ho_Chi_Minh")
                ) + timedelta(minutes=settings.account_lockout_duration_minutes)

            user.updated_at = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
            async with DatabaseSession() as session:
                await session.flush()
                await _invalidate_user_cache(user)
            return user
        except Exception as e:
            logger.error(f"Error incrementing failed login attempts: {str(e)}")
            raise DatabaseException("Failed to update login attempts")

    async def reset_failed_login_attempts(self, user_id: str) -> None:
        """Reset failed login attempts after successful login"""
        try:
            async with DatabaseSession() as session:
                stmt = (
                    update(User)
                    .where(User.id == uuid.UUID(user_id))
                    .values(failed_login_attempts=0, account_locked_until=None)
                    .returning(User)
                )
                result = await session.execute(stmt)
                await session.commit()

                user = result.scalar_one_or_none()
                if user:
                    await _invalidate_user_cache(user)
        except Exception as e:
            logger.error(f"Error resetting failed login attempts: {str(e)}")
            raise DatabaseException("Failed to reset login attempts")

    async def is_account_locked(self, user: User) -> bool:
        """Check if account is currently locked"""
        if not user.account_locked_until:
            return False

        if datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")) > user.account_locked_until:
            await self.reset_failed_login_attempts(str(user.id))
            return False

        return True

    async def assign_default_permissions(self, user_id: uuid.UUID) -> None:
        """Assign default permissions to a new user"""
        try:
            default_perms = ROLE_PERMISSIONS.get("user", [])

            async with DatabaseSession() as session:
                for perm_name in default_perms:
                    permission_result = await session.execute(
                        select(Permission).where(Permission.name == perm_name)
                    )
                    permission = permission_result.scalar_one_or_none()

                    if permission:
                        user_permission = UserPermission(
                            user_id=user_id,
                            permission_id=permission.id,
                            granted_at=datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")),
                        )
                        session.add(user_permission)

                    await session.flush()

        except Exception as e:
            logger.error(f"Error assigning default permissions: {str(e)}")

    async def count_users(self) -> int:
        """Count all users"""
        try:
            async with DatabaseSession() as session:
                result = await session.execute(select(func.count(User.id)))
            return result.scalar_one()
        except Exception as e:
            logger.error(f"Error counting users: {str(e)}")
            raise DatabaseException("Failed to count users")

    async def get_users(self, offset: int, limit: int, order_by: Any) -> List[User]:
        """Get users with pagination"""
        try:
            async with DatabaseSession() as session:
                result = await session.execute(
                    select(User).offset(offset).limit(limit).order_by(order_by)
                )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error getting users: {str(e)}")
            raise DatabaseException("Failed to get users")

    async def username_exists(self, username: str) -> bool:
        """Check if username exists"""
        try:
            async with DatabaseSession() as session:
                result = await session.execute(
                    select(User).where(User.username == username)
                )
                return result.scalars().first() is not None
        except Exception as e:
            logger.error(f"Error checking username exists: {str(e)}")
            raise DatabaseException("Failed to check username exists")

    async def create_oauth_user(self, user_data: dict) -> User:
        """Create user from OAuth data"""
        try:
            async with DatabaseSession() as session:
                original_username = user_data["username"]
                username = original_username
                counter = 1

                while await self.username_exists(username):
                    username = f"{original_username}{counter}"
                    counter += 1

                user_data["username"] = username

                user = User(**user_data)
                session.add(user)
                await session.commit()
                await session.refresh(user)
                return user
        except Exception as e:
            logger.error(f"Error creating OAuth user: {str(e)}")
            raise DatabaseException("Failed to create OAuth user")


class RefreshTokenRepository:
    """Refresh token database operations"""

    async def create_refresh_token(
        self,
        user_id: str,
        token_hash: str,
        expires_at: datetime,
    ) -> RefreshToken:
        """Create a new refresh token"""
        try:
            refresh_token = RefreshToken(
                user_id=uuid.UUID(user_id),
                token_hash=token_hash,
                expires_at=expires_at,
                created_at=datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")),
            )

            async with DatabaseSession() as session:
                session.add(refresh_token)
                await session.flush()
                await session.refresh(refresh_token)

            return refresh_token
        except Exception as e:
            logger.error(f"Error creating refresh token: {str(e)}")
            raise DatabaseException("Failed to create refresh token")

    async def get_refresh_token(self, token_hash: str) -> Optional[RefreshToken]:
        """Get refresh token by hash"""
        try:
            async with DatabaseSession() as session:
                result = await session.execute(
                    select(RefreshToken)
                    .options(selectinload(RefreshToken.user))
                    .where(
                        and_(
                            RefreshToken.token_hash == token_hash,
                            not RefreshToken.is_revoked,
                            RefreshToken.expires_at
                            > datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")),
                        )
                    )
                )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting refresh token: {str(e)}")
            raise DatabaseException("Failed to retrieve refresh token")

    async def revoke_refresh_token(self, token_hash: str) -> bool:
        """Revoke a refresh token"""
        try:
            async with DatabaseSession() as session:
                stmt = (
                    update(RefreshToken)
                    .where(RefreshToken.token_hash == token_hash)
                    .values(
                        is_revoked=True,
                        revoked_at=datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")),
                    )
                    .returning(RefreshToken)
                )
                result = await session.execute(stmt)
                await session.commit()

            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error revoking refresh token: {str(e)}")
            raise DatabaseException("Failed to revoke refresh token")

    async def revoke_all_user_tokens(self, user_id: str) -> int:
        """Revoke all refresh tokens for a user"""
        try:
            async with DatabaseSession() as session:
                stmt = (
                    update(RefreshToken)
                    .where(RefreshToken.user_id == uuid.UUID(user_id))
                    .values(
                        is_revoked=True,
                        revoked_at=datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")),
                    )
                    .returning(RefreshToken)
                )
                result = await session.execute(stmt)
                await session.commit()

            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error revoking all user tokens: {str(e)}")
            raise DatabaseException("Failed to revoke user tokens")

    async def cleanup_expired_tokens(self) -> int:
        """Clean up expired refresh tokens"""
        try:
            async with DatabaseSession() as session:
                stmt = (
                    delete(RefreshToken)
                    .where(
                        RefreshToken.expires_at
                        < datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
                    )
                    .returning(RefreshToken)
                )
                result = await session.execute(stmt)
                await session.commit()

            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error cleaning up expired tokens: {str(e)}")
            raise DatabaseException("Failed to cleanup expired tokens")


class LoginAttemptRepository:
    """Login attempt tracking"""

    async def record_login_attempt(
        self,
        email: str,
        success: bool,
        failure_reason: Optional[str] = None,
    ) -> LoginAttempt:
        """Record a login attempt"""
        try:
            attempt = LoginAttempt(
                email=email.lower(),
                success=success,
                failure_reason=failure_reason,
                attempted_at=datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")),
            )

            async with DatabaseSession() as session:
                session.add(attempt)
                await session.flush()

            return attempt
        except Exception as e:
            logger.error(f"Error recording login attempt: {str(e)}")


def _user_to_cache(u: User) -> dict:
    return {
        "id": str(u.id),
        "email": u.email,
        "username": u.username,
        "full_name": u.full_name,
        "hashed_password": u.hashed_password,
        "role": u.role.value if hasattr(u.role, "value") else u.role,
        "status": u.status.value if hasattr(u.status, "value") else u.status,
        "email_verified": u.email_verified,
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "updated_at": u.updated_at.isoformat() if u.updated_at else None,
        "last_login_at": u.last_login_at.isoformat()
        if getattr(u, "last_login_at", None)
        else None,
        "failed_login_attempts": u.failed_login_attempts,
        "account_locked_until": u.account_locked_until.isoformat()
        if getattr(u, "account_locked_until", None)
        else None,
    }


def _user_from_cache(d: dict) -> User:
    def parse_dt(s):
        return datetime.fromisoformat(s) if s else None

    return User(
        id=uuid.UUID(d["id"]),
        email=d["email"],
        username=d["username"],
        full_name=d["full_name"],
        hashed_password=d.get("hashed_password"),
        role=d.get("role"),
        status=d.get("status"),
        email_verified=d.get("email_verified", False),
        created_at=parse_dt(d.get("created_at")),
        updated_at=parse_dt(d.get("updated_at")),
        last_login_at=parse_dt(d.get("last_login_at")),
        failed_login_attempts=d.get("failed_login_attempts", 0),
        account_locked_until=parse_dt(d.get("account_locked_until")),
    )


async def _invalidate_user_cache(user: User, old_email: Optional[str] = None):
    await redis_client.del_key(USER_BY_ID, str(user.id))
    await redis_client.del_key(USER_BY_EMAIL, (old_email or user.email).lower())
