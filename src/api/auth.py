# src/api/auth.py
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlencode
import secrets
import json
from typing import Optional

from fastapi import APIRouter, Body, Depends, Query, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
import httpx

from src.dependencies.auth import get_current_user, require_admin
from src.core.config.settings import settings
from src.database.models.user import User, UserStatus
from src.domain.schemas.auth import (
    EmailVerificationRequest,
    PasswordChangeRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    TokenRefreshRequest,
    UserLoginRequest,
    UserProfileResponse,
    UserRegistrationRequest,
)
from src.services.auth_service import AuthService
from src.core.security import TokenManager
from src.infrastructure.cache import redis_client
from src.utils.logger_conf import logger


class GoogleOAuthRequest(BaseModel):
    id_token: str


class GoogleOAuthCodeRequest(BaseModel):
    code: str
    redirect_uri: str


router = APIRouter(prefix="/auth", tags=["Authentication"])
auth_service = AuthService()


@router.get("/google/login")
async def google_oauth_redirect(
    redirect_uri: Optional[str] = Query(
        None, description="Frontend redirect URI after OAuth"
    ),
):
    """
    Initiate Google OAuth flow
    This endpoint redirects user to Google's OAuth consent screen
    """
    try:
        state = secrets.token_urlsafe(32)

        oauth_params = {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.oauth_redirect_url,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "offline",
            "state": state,
            "prompt": "select_account",
        }

        google_oauth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(oauth_params)}"
        )

        redirect_uri = redirect_uri or settings.frontend_url

        await redis_client.get().set(
            f"oauth_state:{state}", json.dumps({"redirect_uri": redirect_uri}), ex=600
        )

        return RedirectResponse(url=google_oauth_url)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/google/callback")
async def google_oauth_callback(
    code: str = Query(...),
    state: str = Query(None),
):
    """
    Google OAuth callback - exchanges Google code for our temporary auth code
    """
    stored = await redis_client.get().get(f"oauth_state:{state}")
    if not stored:
        raise HTTPException(400, "Invalid or expired OAuth state")

    data = json.loads(stored)
    redirect_uri = data["redirect_uri"]
    await redis_client.get().delete(f"oauth_state:{state}")

    try:
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.oauth_redirect_url,
            "grant_type": "authorization_code",
        }

        async with httpx.AsyncClient() as client:
            token_response = await client.post(token_url, data=token_data)

            if token_response.status_code != 200:
                raise HTTPException(400, "Failed to exchange code for tokens")

            tokens = token_response.json()
            google_id_token = tokens.get("id_token")

            if not google_id_token:
                raise HTTPException(400, "No ID token received")

        idinfo = id_token.verify_oauth2_token(
            google_id_token,
            google_requests.Request(),
            settings.google_client_id,
            clock_skew_in_seconds=10,
        )

        if idinfo["iss"] not in ["accounts.google.com", "https://accounts.google.com"]:
            raise HTTPException(400, "Invalid token issuer")

        google_user_id = idinfo["sub"]
        email = idinfo["email"]
        full_name = idinfo.get("name", "")
        email_verified = idinfo.get("email_verified", False)
        picture = idinfo.get("picture", "")

        existing_user = await auth_service.get_user_by_email(email)

        if existing_user:
            if existing_user.auth_provider == "local":
                await auth_service.link_google_account(
                    existing_user.id, google_user_id, picture
                )
                user = existing_user
            elif existing_user.auth_provider == "google":
                if existing_user.google_id != google_user_id:
                    raise HTTPException(400, "Google account mismatch")
                user = existing_user
            else:
                raise HTTPException(
                    400,
                    f"Email already exists with {existing_user.auth_provider} provider",
                )
        else:
            user_data = {
                "email": email,
                "username": email.split("@")[0],
                "full_name": full_name,
                "auth_provider": "google",
                "google_id": google_user_id,
                "avatar_url": picture,
                "email_verified": email_verified,
                "status": UserStatus.ACTIVE
                if email_verified
                else UserStatus.PENDING_VERIFICATION,
            }
            user = await auth_service.create_oauth_user(user_data)

        await auth_service.update_user(
            str(user.id), {"last_login_at": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))}
        )

        token_response = await auth_service.generate_tokens(user)

        auth_code = secrets.token_urlsafe(32)

        await redis_client.get().set(
            f"auth_code:{auth_code}",
            json.dumps(
                {
                    "access_token": token_response.access_token,
                    "refresh_token": token_response.refresh_token,
                    "token_type": token_response.token_type,
                    "user_id": str(user.id),
                }
            ),
            ex=300,
        )

        redirect_url = f"{redirect_uri}?code={auth_code}"
        return RedirectResponse(url=redirect_url)

    except Exception as e:
        logger.error(f"OAuth callback error: {str(e)}")
        error_url = f"{redirect_uri}/auth/error?error={str(e)}"
        return RedirectResponse(url=error_url)


@router.post("/exchange-code")
async def exchange_auth_code(code: str = Body(..., embed=True)):
    """
    Exchange temporary authorization code for access & refresh tokens
    Frontend calls this immediately after OAuth redirect
    """
    stored = await redis_client.get().get(f"auth_code:{code}")

    if not stored:
        raise HTTPException(
            status_code=400, detail="Invalid or expired authorization code"
        )

    data = json.loads(stored)
    await redis_client.get().delete(f"auth_code:{code}")

    return {
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "token_type": data["token_type"],
        "user_id": data["user_id"],
    }


@router.post("/register")
async def register(registration_data: UserRegistrationRequest):
    """Register a new user with email/password"""
    try:
        user = await auth_service.register_user(registration_data)
        return {
            "data": user.model_dump(),
            "message": "User registered successfully. Please check your email for verification.",
        }
    except Exception as e:
        raise e


@router.post("/login")
async def login(login_data: UserLoginRequest):
    """Authenticate user with email/password and return JWT tokens"""
    try:
        user, token_response = await auth_service.authenticate_user(login_data)
        return {
            "data": token_response.model_dump(),
            "message": "Login successful",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "username": user.username,
                "full_name": user.full_name,
                "avatar_url": user.avatar_url,
                "auth_provider": user.auth_provider,
            },
        }
    except Exception as e:
        raise e


@router.post("/refresh")
async def refresh_token(refresh_data: TokenRefreshRequest):
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
        raise e


@router.post("/logout")
async def logout(refresh_token: str = Body(..., embed=True)):
    """Logout user by revoking refresh token"""
    try:
        success = await auth_service.logout_user(refresh_token)
        if success:
            return "Logout successful"
        else:
            return "Logout failed - token not found"
    except Exception as e:
        raise e


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user profile"""
    return UserProfileResponse(
        id=str(current_user.id),
        email=current_user.email,
        username=current_user.username,
        full_name=current_user.full_name,
        role=current_user.role,
        status=current_user.status,
        email_verified=current_user.email_verified,
        created_at=current_user.created_at,
        last_login_at=current_user.last_login_at,
    )


@router.post("/logout-all")
async def logout_all_sessions(current_user: User = Depends(get_current_user)):
    """Logout user from all sessions"""
    try:
        revoked_count = await auth_service.logout_all_sessions(str(current_user.id))
        return f"Logged out from {revoked_count} sessions"
    except Exception as e:
        raise e


@router.get("/profile")
async def get_profile(current_user: User = Depends(get_current_user)):
    """Get current user profile with permissions"""
    try:
        profile = await auth_service.get_user_profile(str(current_user.id))
        return profile.model_dump()
    except Exception as e:
        raise e


@router.put("/profile")
async def update_profile(
    profile_data: dict = Body(...),
    current_user: User = Depends(get_current_user),
):
    """Update current user profile"""
    try:
        allowed_fields = {"full_name", "username"}
        update_data = {k: v for k, v in profile_data.items() if k in allowed_fields}

        if not update_data:
            return "No valid fields provided for update"

        updated_user = await auth_service.update_user(str(current_user.id), update_data)

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
        raise e


@router.post("/password/change")
async def change_password(
    password_data: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
):
    """Change user password (only for local auth users)"""
    try:
        success = await auth_service.change_password(
            str(current_user.id), password_data
        )
        if success:
            return "Password changed successfully"
        else:
            return "Password change failed"
    except Exception as e:
        raise e


@router.post("/password/reset")
async def request_password_reset(reset_data: PasswordResetRequest):
    """Request password reset"""
    try:
        await auth_service.request_password_reset(reset_data.email)
        return "If the email exists, a password reset link has been sent"
    except Exception as e:
        raise e


@router.post("/password/reset/confirm")
async def confirm_password_reset(reset_data: PasswordResetConfirmRequest):
    """Confirm password reset with token"""
    try:
        success = await auth_service.reset_password(reset_data)
        if success:
            return "Password reset successful"
        else:
            return "Password reset failed"
    except Exception as e:
        raise e


@router.post("/email/verify")
async def verify_email(verification_data: EmailVerificationRequest):
    """Verify user email with token"""
    try:
        user = await auth_service.verify_email(verification_data.token)
        return user.model_dump()
    except Exception as e:
        raise e


@router.post("/email/resend-verification")
async def resend_verification_email(current_user: User = Depends(get_current_user)):
    """Resend email verification"""
    try:
        if current_user.email_verified:
            return "Email is already verified"

        verification_token, expires_at = TokenManager.create_verification_token()

        await auth_service.update_user(
            str(current_user.id),
            {
                "email_verification_token": verification_token,
                "email_verification_expires": expires_at,
            },
        )

        await auth_service.send_verification_email(current_user)
        return "Verification email sent"
    except Exception as e:
        raise e


@router.get("/users")
async def list_users(
    page: int = 1,
    size: int = 10,
    admin_user: User = Depends(require_admin),
):
    """List all users (admin only)"""
    try:
        offset = (page - 1) * size
        users = await auth_service.get_users(
            offset=offset, limit=size, order_by=User.created_at.desc()
        )

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
        raise e


@router.get("/validate")
async def validate_token(current_user: User = Depends(get_current_user)):
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
