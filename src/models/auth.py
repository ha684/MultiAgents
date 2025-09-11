# src/models/auth.py
from pydantic import BaseModel, EmailStr, Field, model_validator
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"
    MODERATOR = "moderator"


class UserStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING_VERIFICATION = "pending_verification"


# Request Models
class UserRegistrationRequest(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50, pattern="^[a-zA-Z0-9_-]+$")
    password: str = Field(..., min_length=8, max_length=128)
    full_name: Optional[str] = Field(None, max_length=100)

    @model_validator(mode='after')
    def validate_password_comprehensive(self):
        """Validate password with all errors at once"""
        password = self.password
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
            raise ValueError(error_message)
        
        return self

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

    @model_validator(mode='after')
    def validate_password_comprehensive(self):
        """Validate password with all errors at once"""
        password = self.password
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
            raise ValueError(error_message)
        
        return self
    
class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)


class EmailVerificationRequest(BaseModel):
    token: str


class OAuthCallbackRequest(BaseModel):
    provider: str = Field(..., pattern="^(google|github)$")
    code: str
    state: Optional[str] = None


# Response Models
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    role: UserRole


class UserProfileResponse(BaseModel):
    id: str
    email: str
    username: str
    full_name: Optional[str]
    role: UserRole
    status: UserStatus
    email_verified: bool
    created_at: datetime
    last_login_at: Optional[datetime]

    class Config:
        from_attributes = True


class UserSessionResponse(BaseModel):
    id: str
    session_id: str
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: datetime
    last_activity: datetime
    expires_at: datetime
    is_active: bool

    class Config:
        from_attributes = True


class PermissionResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    resource: str
    action: str

    class Config:
        from_attributes = True


class UserPermissionResponse(BaseModel):
    permission: PermissionResponse
    granted_at: datetime
    expires_at: Optional[datetime]
    resource_id: Optional[str]

    class Config:
        from_attributes = True


class UserWithPermissionsResponse(UserProfileResponse):
    permissions: List[UserPermissionResponse] = []


# Standard API Response Models
class StandardResponse(BaseModel):
    """Standard API response format"""

    success: bool
    message: str
    data: Optional[Union[Dict[str, Any], List[Dict[str, Any]], Any]] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    request_id: Optional[str] = None
    status_code: int = 200

    class Config:
        json_encoders = {datetime: lambda dt: dt.isoformat()}


class PaginatedResponse(BaseModel):
    success: bool = True
    message: str = "Success"
    data: List[Any]
    pagination: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    error_code: Optional[str] = None
    errors: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


# JWT Token Claims
class TokenData(BaseModel):
    user_id: str
    email: str
    role: UserRole
    session_id: str
    exp: int
    iat: int
    jti: str  # JWT ID for token tracking


# Multi-layer Access Control Models
class ResourcePermissionCheck(BaseModel):
    resource: str  # e.g., 'document', 'knowledge_base'
    action: str  # e.g., 'read', 'write', 'delete'
    resource_id: Optional[str] = None  # Specific resource ID


class AccessControlContext(BaseModel):
    user_id: str
    role: UserRole
    permissions: List[str]
    resource_permissions: Dict[str, List[str]] = {}  # resource_id -> [permissions]


# Rate Limiting Models
class RateLimitInfo(BaseModel):
    limit: int
    remaining: int
    reset_time: datetime
    retry_after: Optional[int] = None


# Health Check Models
class HealthCheckResponse(BaseModel):
    status: str
    timestamp: datetime
    version: str
    services: Dict[str, str]  # service_name -> status


# Request Context Models
class RequestContext(BaseModel):
    request_id: str
    user_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    timestamp: datetime
    correlation_id: Optional[str] = None
