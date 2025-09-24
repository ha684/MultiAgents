# src/services/auth_service.py
from datetime import datetime, timedelta
from typing import Any, List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import and_, select

from src.config.auth_settings import auth_settings
from src.db.models.user import User, UserStatus
from src.db.repository.database_session import DatabaseSession
from src.exceptions.auth_exceptions import (
    AccountLockedException,
    AccountNotVerifiedException,
    AccountSuspendedException,
    InvalidCredentialsException,
    InvalidTokenException,
    RefreshTokenException,
    UserNotFoundException,
)
from src.models.auth import (
    PasswordChangeRequest,
    PasswordResetConfirmRequest,
    TokenData,
    TokenResponse,
    UserLoginRequest,
    UserPermissionResponse,
    UserProfileResponse,
    UserRegistrationRequest,
    UserWithPermissionsResponse,
)
from src.services.security_services import jwt_manager, security_manager, token_manager
from src.services.user_service import (
    LoginAttemptRepository,
    RefreshTokenRepository,
    UserRepository,
)
from src.services.utils import send_password_reset_email
from src.utils.logger_conf import logger


class AuthenticationService:
    """Main authentication service"""

    def __init__(self):
        self.user_repo = UserRepository()
        self.refresh_token_repo = RefreshTokenRepository()
        self.login_attempt_repo = LoginAttemptRepository()
        self.jwt_manager = jwt_manager
        self.security_manager = security_manager
        self.token_manager = token_manager

    async def register_user(
        self,
        registration_data: UserRegistrationRequest,
    ) -> UserProfileResponse:
        """Register a new user"""
        try:
            logger.info(f"Registering new user: {registration_data.email}")
            new_user = await self.user_repo.create_user(registration_data)
            logger.info(f"User registered successfully: {new_user.id}")
            return UserProfileResponse(
                id=str(new_user.id),
                email=new_user.email,
                username=new_user.username,
                full_name=new_user.full_name,
                role=new_user.role,
                status=new_user.status,
                email_verified=new_user.email_verified,
                created_at=new_user.created_at,
                last_login_at=new_user.last_login_at,
            )

        except Exception as e:
            logger.error(f"Registration failed for {registration_data.email}: {str(e)}")
            raise e

    async def authenticate_user(
        self,
        login_data: UserLoginRequest,
    ) -> TokenResponse:
        """Authenticate user and return tokens"""
        try:
            logger.info(f"Authentication attempt for: {login_data.email}")
            user = await self.user_repo.get_user_by_email(login_data.email)
            if not user:
                await self.login_attempt_repo.record_login_attempt(
                    email=login_data.email,
                    success=False,
                    failure_reason="user_not_found",
                )
                raise InvalidCredentialsException()

            if await self.user_repo.is_account_locked(user):
                await self.login_attempt_repo.record_login_attempt(
                    email=login_data.email,
                    success=False,
                    failure_reason="account_locked",
                )
                lock_until = user.account_locked_until
                raise AccountLockedException(
                    unlock_time=lock_until.strftime("%Y-%m-%d %H:%M:%S UTC")
                    if lock_until
                    else None
                )

            if user.status == UserStatus.SUSPENDED:
                await self.login_attempt_repo.record_login_attempt(
                    email=login_data.email,
                    success=False,
                    failure_reason="account_suspended",
                )
                raise AccountSuspendedException()

            if not self.security_manager.verify_password(
                login_data.password, user.hashed_password
            ):
                await self.user_repo.increment_failed_login_attempts(user.email)

                await self.login_attempt_repo.record_login_attempt(
                    email=login_data.email,
                    success=False,
                    failure_reason="invalid_password",
                )

                raise InvalidCredentialsException()

            if (
                not user.email_verified
                and user.status == UserStatus.PENDING_VERIFICATION
            ):
                await self.login_attempt_repo.record_login_attempt(
                    email=login_data.email,
                    success=False,
                    failure_reason="email_not_verified",
                )
                raise AccountNotVerifiedException()

            await self.user_repo.reset_failed_login_attempts(str(user.id))

            await self.user_repo.update_last_login(str(user.id))

            session_id = self.security_manager.generate_session_id()
            access_token = self.jwt_manager.create_access_token(
                user_id=str(user.id),
                email=user.email,
                role=user.role,
                session_id=session_id,
            )

            refresh_token = self.jwt_manager.create_refresh_token()
            refresh_token_hash = self.security_manager.hash_token(refresh_token)

            expires_at = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")) + timedelta(
                days=auth_settings.jwt_refresh_token_expire_days
            )

            await self.refresh_token_repo.create_refresh_token(
                user_id=str(user.id),
                token_hash=refresh_token_hash,
                expires_at=expires_at,
            )

            await self.login_attempt_repo.record_login_attempt(
                email=login_data.email,
                success=True,
            )

            logger.info(f"Authentication successful for user: {user.id}")

            return TokenResponse(
                access_token=access_token,
                refresh_token=refresh_token,
                token_type="bearer",
                expires_in=auth_settings.jwt_access_token_expire_minutes * 60,
                user_id=str(user.id),
                role=user.role,
            )

        except Exception as e:
            logger.error(f"Authentication failed for {login_data.email}: {str(e)}")
            raise

    async def refresh_access_token(self, refresh_token: str) -> TokenResponse:
        """Refresh access token using refresh token"""
        try:
            logger.info("Refreshing access token")
            token_hash = self.security_manager.hash_token(refresh_token)
            stored_token = await self.refresh_token_repo.get_refresh_token(token_hash)
            if not stored_token:
                raise RefreshTokenException("Invalid refresh token")

            if stored_token.is_revoked:
                raise RefreshTokenException("Refresh token has been revoked")

            if stored_token.expires_at <= datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")):
                raise RefreshTokenException("Refresh token has expired")

            user = stored_token.user
            if not user:
                raise RefreshTokenException("User not found for refresh token")

            if user.status != UserStatus.ACTIVE:
                raise RefreshTokenException("User account is not active")

            session_id = self.security_manager.generate_session_id()
            new_access_token = self.jwt_manager.create_access_token(
                user_id=str(user.id),
                email=user.email,
                role=user.role,
                session_id=session_id,
            )

            new_refresh_token = refresh_token
            if auth_settings.jwt_refresh_token_expire_days <= 1:
                new_refresh_token = self.jwt_manager.create_refresh_token()
                new_token_hash = self.security_manager.hash_token(new_refresh_token)

                await self.refresh_token_repo.revoke_refresh_token(token_hash)

                expires_at = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")) + timedelta(
                    days=auth_settings.jwt_refresh_token_expire_days
                )

                await self.refresh_token_repo.create_refresh_token(
                    user_id=str(user.id),
                    token_hash=new_token_hash,
                    expires_at=expires_at,
                )

            logger.info(f"Token refreshed successfully for user: {user.id}")

            return TokenResponse(
                access_token=new_access_token,
                refresh_token=new_refresh_token,
                token_type="bearer",
                expires_in=auth_settings.jwt_access_token_expire_minutes * 60,
                user_id=str(user.id),
                role=user.role,
            )

        except Exception as e:
            logger.error(f"Token refresh failed: {str(e)}")
            raise

    async def logout_user(self, refresh_token: str) -> bool:
        """Logout user by revoking refresh token"""
        try:
            token_hash = self.security_manager.hash_token(refresh_token)
            revoked = await self.refresh_token_repo.revoke_refresh_token(token_hash)

            if revoked:
                logger.info("User logged out successfully")

            return revoked

        except Exception as e:
            logger.error(f"Logout failed: {str(e)}")
            return False

    async def logout_all_sessions(self, user_id: str) -> int:
        """Logout user from all sessions"""
        try:
            revoked_count = await self.refresh_token_repo.revoke_all_user_tokens(
                user_id
            )
            logger.info(f"Logged out user from {revoked_count} sessions")
            return revoked_count

        except Exception as e:
            logger.error(f"Logout all sessions failed: {str(e)}")
            return 0

    async def verify_email(self, token: str) -> UserProfileResponse:
        """Verify user email with token"""
        try:
            user = await self.user_repo.verify_email(token)
            if not user:
                raise InvalidTokenException("Invalid or expired verification token")

            logger.info(f"Email verified for user: {user.id}")

            return UserProfileResponse(
                id=str(user.id),
                email=user.email,
                username=user.username,
                full_name=user.full_name,
                role=user.role,
                status=user.status,
                email_verified=user.email_verified,
                created_at=user.created_at,
                last_login_at=user.last_login_at,
            )

        except Exception as e:
            logger.error(f"Email verification failed: {str(e)}")
            raise

    async def request_password_reset(self, email: str) -> bool:
        """Request password reset"""
        try:
            user = await self.user_repo.get_user_by_email(email)
            if not user:
                logger.info(f"Password reset requested for non-existent user: {email}")
                return True

            reset_token, expires_at = self.token_manager.create_verification_token()

            await self.user_repo.update_user(
                str(user.id),
                {
                    "password_reset_token": reset_token,
                    "password_reset_expires": expires_at,
                },
            )

            await send_password_reset_email(user, reset_token)

            logger.info(f"Password reset requested for user: {user.id}")
            return True

        except Exception as e:
            logger.error(f"Password reset request failed for {email}: {str(e)}")
            return False

    async def reset_password(self, reset_data: PasswordResetConfirmRequest) -> bool:
        """Reset password with token"""
        try:
            user = None
            async with DatabaseSession() as session:
                user = await session.execute(
                    select(User).where(
                        and_(
                            User.password_reset_token == reset_data.token,
                            User.password_reset_expires
                            > datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")),
                        )
                    )
                )
                user = user.scalar_one_or_none()

            if not user:
                raise InvalidTokenException("Invalid or expired reset token")

            new_password_hash = self.security_manager.hash_password(
                reset_data.new_password
            )

            await self.user_repo.update_user(
                str(user.id),
                {
                    "hashed_password": new_password_hash,
                    "password_reset_token": None,
                    "password_reset_expires": None,
                    "failed_login_attempts": 0,
                    "account_locked_until": None,
                },
            )

            await self.refresh_token_repo.revoke_all_user_tokens(str(user.id))

            logger.info(f"Password reset successful for user: {user.id}")
            return True

        except Exception as e:
            logger.error(f"Password reset failed: {str(e)}")
            raise

    async def change_password(
        self, user_id: str, change_data: PasswordChangeRequest
    ) -> bool:
        """Change user password"""
        try:
            user = await self.user_repo.get_user_by_id(user_id)
            if not user:
                raise UserNotFoundException()

            if not self.security_manager.verify_password(
                change_data.current_password, user.hashed_password
            ):
                raise InvalidCredentialsException("Current password is incorrect")

            new_password_hash = self.security_manager.hash_password(
                change_data.new_password
            )

            await self.user_repo.update_user(
                user_id, {"hashed_password": new_password_hash}
            )

            await self.refresh_token_repo.revoke_all_user_tokens(user_id)

            logger.info(f"Password changed for user: {user.id}")
            return True

        except Exception as e:
            logger.error(f"Password change failed for user {user_id}: {str(e)}")
            raise

    async def get_user_profile(self, user_id: str) -> UserWithPermissionsResponse:
        """Get user profile with permissions"""
        try:
            user = await self.user_repo.get_user_with_permissions(user_id)
            if not user:
                raise UserNotFoundException()

            permissions = []
            for user_perm in user.user_permissions:
                permissions.append(
                    UserPermissionResponse(
                        permission=user_perm.permission,
                        granted_at=user_perm.granted_at,
                        expires_at=user_perm.expires_at,
                        resource_id=user_perm.resource_id,
                    )
                )

            return UserWithPermissionsResponse(
                id=str(user.id),
                email=user.email,
                username=user.username,
                full_name=user.full_name,
                role=user.role,
                status=user.status,
                email_verified=user.email_verified,
                created_at=user.created_at,
                last_login_at=user.last_login_at,
                permissions=permissions,
            )

        except Exception as e:
            logger.error(f"Get user profile failed for {user_id}: {str(e)}")
            raise

    async def validate_token(self, token: str) -> Optional[TokenData]:
        """Validate JWT token and return token data"""
        try:
            return self.jwt_manager.verify_token(token)
        except Exception as e:
            logger.error(f"Token validation failed: {str(e)}")
            return None

    async def update_user(self, user_id: str, update_data: dict) -> UserProfileResponse:
        """Update user profile"""
        try:
            user = await self.user_repo.update_user(user_id, update_data)
            return UserProfileResponse(
                id=str(user.id),
                email=user.email,
                username=user.username,
                full_name=user.full_name,
                role=user.role,
                status=user.status,
                email_verified=user.email_verified,
                created_at=user.created_at,
                last_login_at=user.last_login_at,
            )
        except Exception as e:
            logger.error(f"Update user profile failed for {user_id}: {str(e)}")
            raise

    async def count_users(self) -> int:
        """Count all users"""
        return await self.user_repo.count_users()

    async def get_users(self, offset: int, limit: int, order_by: Any) -> List[User]:
        """Get users with pagination"""
        return await self.user_repo.get_users(offset, limit, order_by)
