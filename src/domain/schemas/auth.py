# src/domain/schemas/auth.py
import re
from datetime import datetime
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from src.core.exceptions.auth_exceptions import (
    FullNameValidationException,
    PasswordValidationException,
    UsernameValidationException,
)


# Enums
class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"
    MODERATOR = "moderator"


class UserStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING_VERIFICATION = "pending_verification"


# Authentication Request Models
class UserRegistrationRequest(BaseModel):
    email: EmailStr
    username: str
    password: str
    full_name: str | None = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate the username with all errors at once."""
        errors = []
        if len(v) < 3:
            errors.append("Username must be at least 3 characters long")
        if len(v) > 50:
            errors.append("Username must be no more than 50 characters long")
        if not re.match("^[a-zA-Z0-9_-]+$", v):
            errors.append(
                "Username can only contain letters, numbers, underscores, and hyphens"
            )

        if errors:
            raise UsernameValidationException(message=". ".join(errors))
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate the password with all errors at once."""
        errors = []
        if len(v) < 8:
            errors.append("Password must be at least 8 characters long")
        if len(v) > 128:
            errors.append("Password must be no more than 128 characters long")
        if not any(c.isupper() for c in v):
            errors.append("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            errors.append("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            errors.append("Password must contain at least one digit")
        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in v):
            errors.append("Password must contain at least one special character")

        if errors:
            raise PasswordValidationException(message=". ".join(errors))
        return v

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str | None) -> str | None:
        """Validate the full_name if it's provided."""
        if v is not None:
            errors = []
            if len(v.strip()) == 0:
                errors.append("Full name cannot be empty or just spaces")
            if len(v) > 100:
                errors.append("Full name must be no more than 100 characters long")

            if errors:
                raise FullNameValidationException(message=". ".join(errors))
        return v


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)
    remember_me: bool = False


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_password_comprehensive(self):
        """Validate password with all errors at once"""
        password = self.new_password
        errors = []

        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")

        if not any(c.isupper() for c in password):
            errors.append("Password must contain at least one uppercase letter")

        if not any(c.islower() for c in password):
            errors.append("Password must contain at least one lowercase letter")

        if not any(c.isdigit() for c in password):
            errors.append("Password must contain at least one digit")

        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
            errors.append("Password must contain at least one special character")

        if errors:
            error_message = ". ".join(errors)
            raise PasswordValidationException(message=error_message)

        return self


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)


class EmailVerificationRequest(BaseModel):
    token: str


class OAuthCallbackRequest(BaseModel):
    provider: str = Field(..., pattern="^(google|github)$")
    code: str
    state: str | None = None


# Response Models
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserProfileResponse(BaseModel):
    id: str
    email: str
    username: str
    full_name: str | None
    role: UserRole
    status: UserStatus
    email_verified: bool
    created_at: datetime
    last_login_at: datetime | None

    class Config:
        from_attributes = True


class UserSessionResponse(BaseModel):
    id: str
    session_id: str
    ip_address: str | None
    user_agent: str | None
    created_at: datetime
    last_activity: datetime
    expires_at: datetime
    is_active: bool

    class Config:
        from_attributes = True


class PermissionResponse(BaseModel):
    id: str
    name: str
    description: str | None
    resource: str
    action: str

    class Config:
        from_attributes = True


class UserPermissionResponse(BaseModel):
    permission: PermissionResponse
    granted_at: datetime
    expires_at: datetime | None
    resource_id: str | None

    class Config:
        from_attributes = True


class UserWithPermissionsResponse(UserProfileResponse):
    permissions: list[UserPermissionResponse] = []


class StandardResponse(BaseModel):
    """Standard API response format"""

    success: bool
    message: str
    data: dict[str, Any] | list[dict[str, Any]] | Any | None = None
    timestamp: datetime = Field(
        default_factory=datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    )
    request_id: str | None = None
    status_code: int = 200

    class Config:
        json_encoders = {datetime: lambda dt: dt.isoformat()}


class PaginatedResponse(BaseModel):
    success: bool = True
    message: str = "Success"
    data: list[Any]
    pagination: dict[str, Any]
    metadata: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    error_code: str | None = None
    errors: list[str] | None = None
    metadata: dict[str, Any] | None = None


# Internal Models
class TokenData(BaseModel):
    user_id: str
    email: str
    role: UserRole
    session_id: str
    exp: int
    iat: int
    jti: str


class ResourcePermissionCheck(BaseModel):
    resource: str  # e.g., 'document', 'knowledge_base'
    action: str  # e.g., 'read', 'write', 'delete'
    resource_id: str | None = None  # Specific resource ID


class AccessControlContext(BaseModel):
    user_id: str
    role: UserRole
    permissions: list[str]
    resource_permissions: dict[str, list[str]] = {}  # resource_id -> [permissions]


class RateLimitInfo(BaseModel):
    limit: int
    remaining: int
    reset_time: datetime
    retry_after: int | None = None


class RequestContext(BaseModel):
    request_id: str
    user_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    timestamp: datetime
    correlation_id: str | None = None
    timestamp: datetime
    correlation_id: str | None = None
