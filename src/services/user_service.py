# src/services/user_service.py
from typing import Optional, Dict, Any, List
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import and_, update, delete, func
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import uuid
from src.db.repository.database_session import DatabaseSession
from src.services.security_services import token_manager
from src.db.models.user import (
    User,
    RefreshToken,
    Permission,
    UserPermission,
    LoginAttempt,
    UserRole,
    UserStatus,
)
from src.models.auth import UserRegistrationRequest
from src.services.security_services import security_manager
from src.config.auth_settings import auth_settings, ROLE_PERMISSIONS
from src.exceptions.auth_exceptions import (
    UserNotFoundException,
    UserAlreadyExistsException,
    DatabaseException,
)
from src.utils.decorators import singleton
from src.utils.logger_conf import logger


@singleton
class UserRepository:
    """User database operations"""

    async def create_user(self, user_data: UserRegistrationRequest) -> User:
        """Create a new user"""
        try:
            existing_user = await self.get_user_by_email(user_data.email)
            if existing_user:
                raise UserAlreadyExistsException("User with this email already exists")

            hashed_password = security_manager.hash_password(user_data.password)

            verification_token, verification_expires = (
                token_manager.create_verification_token()
            )

            new_user = User(
                id=uuid.uuid4(),
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

            await self.assign_default_permissions(new_user.id)

            return new_user

        except Exception as e:
            logger.error(f"Error creating user: {str(e)}")
            if isinstance(e, (UserAlreadyExistsException,)):
                raise
            raise DatabaseException("Failed to create user")

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        try:
            async with DatabaseSession() as session:
                result = await session.execute(
                    select(User).where(User.email == email.lower())
                )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting user by email: {str(e)}")
            raise DatabaseException("Failed to retrieve user")

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID"""
        try:
            async with DatabaseSession() as session:
                result = await session.execute(
                    select(User).where(User.id == uuid.UUID(user_id))
                )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting user by ID: {str(e)}")
            raise DatabaseException("Failed to retrieve user")

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
            user = await self.get_user_by_id(user_id)
            if not user:
                raise UserNotFoundException()

            # Update fields
            for field, value in update_data.items():
                if hasattr(user, field):
                    setattr(user, field, value)

            user.updated_at = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
            async with DatabaseSession() as session:
                await session.flush()
                await session.refresh(user)

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
            return result.rowcount > 0
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

            return user
        except Exception as e:
            logger.error(f"Error verifying email: {str(e)}")
            raise DatabaseException("Failed to verify email")

    async def update_last_login(self, user_id: str) -> None:
        """Update user's last login timestamp"""
        try:
            async with DatabaseSession() as session:
                await session.execute(
                    update(User)
                    .where(User.id == uuid.UUID(user_id))
                    .values(last_login_at=datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")))
                )
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

            if user.failed_login_attempts >= auth_settings.max_login_attempts:
                user.account_locked_until = datetime.now(
                    ZoneInfo("Asia/Ho_Chi_Minh")
                ) + timedelta(minutes=auth_settings.account_lockout_duration_minutes)

            user.updated_at = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
            async with DatabaseSession() as session:
                await session.flush()

            return user
        except Exception as e:
            logger.error(f"Error incrementing failed login attempts: {str(e)}")
            raise DatabaseException("Failed to update login attempts")

    async def reset_failed_login_attempts(self, user_id: str) -> None:
        """Reset failed login attempts after successful login"""
        try:
            async with DatabaseSession() as session:
                await session.execute(
                    update(User)
                    .where(User.id == uuid.UUID(user_id))
                    .values(failed_login_attempts=0, account_locked_until=None)
                )
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
                            id=uuid.uuid4(),
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
                id=uuid.uuid4(),
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
                result = await session.execute(
                    update(RefreshToken)
                    .where(RefreshToken.token_hash == token_hash)
                    .values(
                        is_revoked=True,
                        revoked_at=datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")),
                    )
                )
            return result.rowcount > 0
        except Exception as e:
            logger.error(f"Error revoking refresh token: {str(e)}")
            raise DatabaseException("Failed to revoke refresh token")

    async def revoke_all_user_tokens(self, user_id: str) -> int:
        """Revoke all refresh tokens for a user"""
        try:
            async with DatabaseSession() as session:
                result = await session.execute(
                    update(RefreshToken)
                    .where(RefreshToken.user_id == uuid.UUID(user_id))
                    .values(
                        is_revoked=True,
                        revoked_at=datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")),
                    )
                )
            return result.rowcount
        except Exception as e:
            logger.error(f"Error revoking all user tokens: {str(e)}")
            raise DatabaseException("Failed to revoke user tokens")

    async def cleanup_expired_tokens(self) -> int:
        """Clean up expired refresh tokens"""
        try:
            async with DatabaseSession() as session:
                result = await session.execute(
                    delete(RefreshToken).where(
                        RefreshToken.expires_at
                        < datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
                    )
                )
            return result.rowcount
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
                id=uuid.uuid4(),
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
