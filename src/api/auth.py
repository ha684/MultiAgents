#src/api/auth.py
from fastapi import APIRouter, Depends, Request, Body
from src.models.auth import (
    UserRegistrationRequest,
    UserLoginRequest,
    TokenRefreshRequest,
    PasswordResetRequest,
    PasswordResetConfirmRequest,
    PasswordChangeRequest,
    EmailVerificationRequest,
    UserProfileResponse,
    StandardResponse,
)
from src.db.models.user import User
from src.services.auth_service import AuthenticationService
from src.auth.dependencies import get_current_user, require_admin
from src.middleware.rate_limit import check_rate_limit, RedisRateLimiter
from src.services.user_service import UserRepository
from src.utils.logger_conf import logger
from src.utils.security import token_manager

router = APIRouter(prefix="/auth", tags=["Authentication"])
rate_limiter = RedisRateLimiter()
auth_service = AuthenticationService()
user_repo = UserRepository()

@router.post("/register", response_model=StandardResponse)
async def register(
    request: Request,
    registration_data: UserRegistrationRequest,
):
    """Register a new user"""
    try:
        await check_rate_limit(
            request,
            registration_data.email,
            limit=5,
            window_minutes=15,
            rate_limiter=rate_limiter,
        )

        user = await auth_service.register_user(
            registration_data,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
        )

        return {
            "data": user.model_dump(),
            "message": "User registered successfully. Please check your email for verification.",
        }

    except Exception as e:
        logger.error(f"Registration failed: {str(e)}")
        raise


@router.post("/login", response_model=StandardResponse)
async def login(
    request: Request,
    login_data: UserLoginRequest,
):
    """Authenticate user and return JWT tokens"""
    try:
        await check_rate_limit(
            request,
            login_data.email,
            limit=10,
            window_minutes=15,
            rate_limiter=rate_limiter,
        )
        token_response = await auth_service.authenticate_user(
            login_data,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
        )

        return {
            "data": token_response.model_dump(),
            "message": "Login successful",
        }

    except Exception as e:
        logger.error(f"Login failed: {str(e)}")
        raise


@router.post("/refresh", response_model=StandardResponse)
async def refresh_token(
    request: Request,
    refresh_data: TokenRefreshRequest,
):
    """Refresh access token using refresh token"""
    try:
        token_response = await auth_service.refresh_access_token(
            refresh_data.refresh_token
        )

        return {
            "data": token_response.model_dump(),
            "message": "Token refreshed successfully",
        }

    except Exception as e:
        logger.error(f"Token refresh failed: {str(e)}")
        raise


@router.post("/logout", response_model=StandardResponse)
async def logout(
    request: Request,
    refresh_token: str = Body(..., embed=True),
):
    """Logout user by revoking refresh token"""
    try:
        success = await auth_service.logout_user(refresh_token)

        if success:
            return "Logout successful"
        else:
            return "Logout failed - token not found"

    except Exception as e:
        logger.error(f"Logout failed: {str(e)}")
        raise


@router.post("/logout-all", response_model=StandardResponse)
async def logout_all_sessions(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Logout user from all sessions"""
    try:
        revoked_count = await auth_service.logout_all_sessions(str(current_user.id))

        return f"Logged out from {revoked_count} sessions"

    except Exception as e:
        logger.error(f"Logout all sessions failed: {str(e)}")
        raise


@router.get("/profile", response_model=StandardResponse)
async def get_profile(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Get current user profile with permissions"""
    try:
        profile = await auth_service.get_user_profile(str(current_user.id))

        return profile.model_dump()

    except Exception as e:
        logger.error(f"Get profile failed: {str(e)}")
        raise


@router.put("/profile", response_model=StandardResponse)
async def update_profile(
    request: Request,
    profile_data: dict = Body(...),
    current_user: User = Depends(get_current_user),
):
    """Update current user profile"""
    try:
        allowed_fields = {"full_name", "username"}
        update_data = {k: v for k, v in profile_data.items() if k in allowed_fields}

        if not update_data:
            return "No valid fields provided for update"

        updated_user = await user_repo.update_user(str(current_user.id), update_data)

        return UserProfileResponse(
            id=str(updated_user.id),
            email=updated_user.email,
            username=updated_user.username,
            full_name=updated_user.full_name,
            role=updated_user.role,
            status=updated_user.status,
            email_verified=updated_user.email_verified,
            created_at=updated_user.created_at,
            last_login_at=updated_user.last_login_at,
        ).model_dump()

    except Exception as e:
        logger.error(f"Profile update failed: {str(e)}")
        raise


@router.post("/password/change", response_model=StandardResponse)
async def change_password(
    request: Request,
    password_data: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
):
    """Change user password"""
    try:
        success = await auth_service.change_password(
            str(current_user.id), password_data
        )

        if success:
            return "Password changed successfully"
        else:
            return "Password change failed"

    except Exception as e:
        logger.error(f"Password change failed: {str(e)}")
        raise


@router.post("/password/reset", response_model=StandardResponse)
async def request_password_reset(
    request: Request,
    reset_data: PasswordResetRequest,
):
    """Request password reset"""
    try:
        await check_rate_limit(
            request,
            reset_data.email,
            limit=3,
            window_minutes=60,
            rate_limiter=rate_limiter,
        )

        await auth_service.request_password_reset(reset_data.email)

        return "If the email exists, a password reset link has been sent"

    except Exception as e:
        logger.error(f"Password reset request failed: {str(e)}")
        raise


@router.post("/password/reset/confirm", response_model=StandardResponse)
async def confirm_password_reset(
    request: Request,
    reset_data: PasswordResetConfirmRequest,
):
    """Confirm password reset with token"""
    try:
        await check_rate_limit(
            request,
            reset_data.token,
            limit=5,
            window_minutes=15,
            rate_limiter=rate_limiter,
        )

        success = await auth_service.reset_password(reset_data)

        if success:
            return "Password reset successful"
        else:
            return "Password reset failed"

    except Exception as e:
        logger.error(f"Password reset confirmation failed: {str(e)}")
        raise


@router.post("/email/verify", response_model=StandardResponse)
async def verify_email(
    request: Request,
    verification_data: EmailVerificationRequest,
):
    """Verify user email with token"""
    try:
        user = await auth_service.verify_email(verification_data.token)

        return user.model_dump()

    except Exception as e:
        logger.error(f"Email verification failed: {str(e)}")
        raise


@router.post("/email/resend-verification", response_model=StandardResponse)
async def resend_verification_email(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Resend email verification"""
    try:
        await check_rate_limit(
            request,
            str(current_user.id),
            limit=3,
            window_minutes=60,
            rate_limiter=rate_limiter,
        )

        if current_user.email_verified:
            return "Email is already verified"

        verification_token, expires_at = token_manager.create_email_verification_token()

        await user_repo.update_user(
            str(current_user.id),
            {
                "email_verification_token": verification_token,
                "email_verification_expires": expires_at,
            },
        )

        # TODO: Send verification email
        # await send_verification_email(current_user.email, verification_token)

        return "Verification email sent"

    except Exception as e:
        logger.error(f"Resend verification email failed: {str(e)}")
        raise


@router.get("/users", response_model=StandardResponse)
async def list_users(
    request: Request,
    page: int = 1,
    size: int = 10,
    admin_user: User = Depends(require_admin),
):
    """List all users (admin only)"""
    try:
        total = await user_repo.count_users()

        offset = (page - 1) * size
        result = await user_repo.get_users(
            offset=offset, limit=size, order_by=User.created_at.desc()
        )
        users = result

        users_data = [
            UserProfileResponse(
                id=str(user.id),
                email=user.email,
                username=user.username,
                full_name=user.full_name,
                role=user.role,
                status=user.status,
                email_verified=user.email_verified,
                created_at=user.created_at,
                last_login_at=user.last_login_at,
            ).model_dump()
            for user in users
        ]

        return users_data

    except Exception as e:
        logger.error(f"List users failed: {str(e)}")
        raise


@router.get("/validate", response_model=StandardResponse)
async def validate_token(
    request: Request, current_user: User = Depends(get_current_user)
):
    """Validate current token and return user info"""
    return {
        "data": {
            "user_id": str(current_user.id),
            "email": current_user.email,
            "role": current_user.role.value,
            "status": current_user.status.value,
        },
        "message": "Token is valid",
    }
