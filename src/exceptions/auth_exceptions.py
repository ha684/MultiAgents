# src/exceptions/auth_exceptions.py
from fastapi import HTTPException, status
from typing import Optional, Dict, Any


class BaseAuthException(HTTPException):
    """Base authentication exception"""

    def __init__(
        self,
        status_code: int,
        detail: str,
        error_code: Optional[str] = None,
        headers: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.error_code = error_code


# Authentication Exceptions
class InvalidCredentialsException(BaseAuthException):
    def __init__(self, detail: str = "Invalid email or password"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            error_code="INVALID_CREDENTIALS",
        )


class TokenExpiredException(BaseAuthException):
    def __init__(self, detail: str = "Token has expired"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            error_code="TOKEN_EXPIRED",
            headers={"WWW-Authenticate": "Bearer"},
        )


class InvalidTokenException(BaseAuthException):
    def __init__(self, detail: str = "Invalid or malformed token"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            error_code="INVALID_TOKEN",
            headers={"WWW-Authenticate": "Bearer"},
        )


class TokenNotFoundException(BaseAuthException):
    def __init__(self, detail: str = "Authentication token required"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            error_code="TOKEN_NOT_FOUND",
            headers={"WWW-Authenticate": "Bearer"},
        )


class RefreshTokenException(BaseAuthException):
    def __init__(self, detail: str = "Invalid or expired refresh token"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            error_code="INVALID_REFRESH_TOKEN",
        )


# Authorization Exceptions
class InsufficientPermissionsException(BaseAuthException):
    def __init__(
        self, detail: str = "Insufficient permissions to access this resource"
    ):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            error_code="INSUFFICIENT_PERMISSIONS",
        )


class RoleNotAuthorizedException(BaseAuthException):
    def __init__(self, required_role: str):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This action requires {required_role} role",
            error_code="ROLE_NOT_AUTHORIZED",
        )


class ResourceAccessDeniedException(BaseAuthException):
    def __init__(self, resource: str):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied to {resource}",
            error_code="RESOURCE_ACCESS_DENIED",
        )


# User Account Exceptions
class UserNotFoundException(BaseAuthException):
    def __init__(self, detail: str = "User not found"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
            error_code="USER_NOT_FOUND",
        )


class UserAlreadyExistsException(BaseAuthException):
    def __init__(self, detail: str = "User with this email already exists"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
            error_code="USER_ALREADY_EXISTS",
        )


class AccountLockedException(BaseAuthException):
    def __init__(self, unlock_time: Optional[str] = None):
        detail = "Account is temporarily locked due to too many failed login attempts"
        if unlock_time:
            detail += f". Try again after {unlock_time}"
        super().__init__(
            status_code=status.HTTP_423_LOCKED,
            detail=detail,
            error_code="ACCOUNT_LOCKED",
        )


class AccountNotVerifiedException(BaseAuthException):
    def __init__(self, detail: str = "Email address not verified"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            error_code="ACCOUNT_NOT_VERIFIED",
        )


class AccountSuspendedException(BaseAuthException):
    def __init__(self, detail: str = "Account has been suspended"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            error_code="ACCOUNT_SUSPENDED",
        )


# Rate Limiting Exceptions
class RateLimitExceededException(BaseAuthException):
    def __init__(
        self, detail: str = "Rate limit exceeded", retry_after: Optional[int] = None
    ):
        headers = {}
        if retry_after:
            headers["Retry-After"] = str(retry_after)
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            error_code="RATE_LIMIT_EXCEEDED",
            headers=headers,
        )


# Validation Exceptions
class ValidationException(BaseAuthException):
    def __init__(self, detail: str, field: Optional[str] = None):
        error_code = "VALIDATION_ERROR"
        if field:
            error_code = f"VALIDATION_ERROR_{field.upper()}"
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
            error_code=error_code,
        )


class WeakPasswordException(ValidationException):
    def __init__(self, detail: str = "Password does not meet security requirements"):
        super().__init__(detail=detail, field="password")


class InvalidEmailException(ValidationException):
    def __init__(self, detail: str = "Invalid email address format"):
        super().__init__(detail=detail, field="email")


# OAuth Exceptions
class OAuthException(BaseAuthException):
    def __init__(self, provider: str, detail: str = "OAuth authentication failed"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"{provider} OAuth error: {detail}",
            error_code="OAUTH_ERROR",
        )


class OAuthProviderException(OAuthException):
    def __init__(self, provider: str, detail: str = "OAuth provider error"):
        super().__init__(provider=provider, detail=detail)


class OAuthStateException(OAuthException):
    def __init__(self, provider: str, detail: str = "Invalid OAuth state"):
        super().__init__(provider=provider, detail=detail)


# Session Exceptions
class SessionExpiredException(BaseAuthException):
    def __init__(self, detail: str = "Session has expired"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            error_code="SESSION_EXPIRED",
        )


class InvalidSessionException(BaseAuthException):
    def __init__(self, detail: str = "Invalid or inactive session"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            error_code="INVALID_SESSION",
        )


# System Exceptions
class DatabaseException(BaseAuthException):
    def __init__(self, detail: str = "Database operation failed"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
            error_code="DATABASE_ERROR",
        )


class ExternalServiceException(BaseAuthException):
    def __init__(self, service: str, detail: str = "External service unavailable"):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{service} service error: {detail}",
            error_code="EXTERNAL_SERVICE_ERROR",
        )


class ConfigurationException(BaseAuthException):
    def __init__(self, detail: str = "System configuration error"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
            error_code="CONFIGURATION_ERROR",
        )
