# src/exceptions/auth_exceptions.py
from fastapi import status
from src.exceptions.base import BaseException
from typing import Optional


class PasswordValidationException(BaseException):
    def __init__(self, message: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=message,
            error_code="PASSWORD_VALIDATION_ERROR",
        )


# Authentication Exceptions
class InvalidCredentialsException(BaseException):
    def __init__(self, message: str = "Invalid email or password"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            message=message,
            error_code="INVALID_CREDENTIALS",
        )


class TokenExpiredException(BaseException):
    def __init__(self, message: str = "Token has expired"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            message=message,
            error_code="TOKEN_EXPIRED",
        )


class InvalidTokenException(BaseException):
    def __init__(self, message: str = "Invalid or malformed token"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            message=message,
            error_code="INVALID_TOKEN",
        )


class TokenNotFoundException(BaseException):
    def __init__(self, message: str = "Authentication token required"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            message=message,
            error_code="TOKEN_NOT_FOUND",
        )


class RefreshTokenException(BaseException):
    def __init__(self, message: str = "Invalid or expired refresh token"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            message=message,
            error_code="INVALID_REFRESH_TOKEN",
        )


# Authorization Exceptions
class InsufficientPermissionsException(BaseException):
    def __init__(
        self, message: str = "Insufficient permissions to access this resource"
    ):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            message=message,
            error_code="INSUFFICIENT_PERMISSIONS",
        )


class RoleNotAuthorizedException(BaseException):
    def __init__(self, required_role: str):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            message=f"This action requires {required_role} role",
            error_code="ROLE_NOT_AUTHORIZED",
        )


class ResourceAccessDeniedException(BaseException):
    def __init__(self, message: str):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            message=message,
            error_code="RESOURCE_ACCESS_DENIED",
        )


# User Account Exceptions
class UserNotFoundException(BaseException):
    def __init__(self, message: str = "User not found"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            message=message,
            error_code="USER_NOT_FOUND",
        )


class UserAlreadyExistsException(BaseException):
    def __init__(self, message: str = "User with this email already exists"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            message=message,
            error_code="USER_ALREADY_EXISTS",
        )


class AccountLockedException(BaseException):
    def __init__(
        self,
        message: str = "Account is temporarily locked due to too many failed login attempts",
        unlock_time: Optional[str] = None,
    ):
        message = "Account is temporarily locked due to too many failed login attempts"
        if unlock_time:
            message += f". Try again after {unlock_time}"
        super().__init__(
            status_code=status.HTTP_423_LOCKED,
            message=message,
            error_code="ACCOUNT_LOCKED",
        )


class AccountNotVerifiedException(BaseException):
    def __init__(self, message: str = "Email address not verified"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            message=message,
            error_code="ACCOUNT_NOT_VERIFIED",
        )


class AccountSuspendedException(BaseException):
    def __init__(self, message: str = "Account has been suspended"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            message=message,
            error_code="ACCOUNT_SUSPENDED",
        )


# Rate Limiting Exceptions
class RateLimitExceededException(BaseException):
    def __init__(
        self, message: str = "Rate limit exceeded", retry_after: Optional[int] = None
    ):
        headers = {}
        if retry_after:
            headers["Retry-After"] = str(retry_after)
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            message=message,
            error_code="RATE_LIMIT_EXCEEDED",
            headers=headers,
        )


# Validation Exceptions
class ValidationException(BaseException):
    def __init__(self, message: str, field: Optional[str] = None):
        error_code = "VALIDATION_ERROR"
        if field:
            error_code = f"VALIDATION_ERROR_{field.upper()}"
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            message=message,
            error_code=error_code,
        )


class WeakPasswordException(ValidationException):
    def __init__(self, message: str = "Password does not meet security requirements"):
        super().__init__(message=message, field="password")


class InvalidEmailException(ValidationException):
    def __init__(self, message: str = "Invalid email address format"):
        super().__init__(message=message, field="email")


# OAuth Exceptions
class OAuthException(BaseException):
    def __init__(self, provider: str, message: str = "OAuth authentication failed"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            message=f"{provider} OAuth error: {message}",
            error_code="OAUTH_ERROR",
        )


class OAuthProviderException(OAuthException):
    def __init__(self, provider: str, message: str = "OAuth provider error"):
        super().__init__(provider=provider, message=message)


class OAuthStateException(OAuthException):
    def __init__(self, provider: str, message: str = "Invalid OAuth state"):
        super().__init__(provider=provider, message=message)


# Session Exceptions
class SessionExpiredException(BaseException):
    def __init__(self, message: str = "Session has expired"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            message=message,
            error_code="SESSION_EXPIRED",
        )


class InvalidSessionException(BaseException):
    def __init__(self, message: str = "Invalid or inactive session"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            message=message,
            error_code="INVALID_SESSION",
        )


# System Exceptions
class DatabaseException(BaseException):
    def __init__(self, message: str = "Database operation failed"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=message,
            error_code="DATABASE_ERROR",
        )


class ExternalServiceException(BaseException):
    def __init__(self, service: str, message: str = "External service unavailable"):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            message=f"{service} service error: {message}",
            error_code="EXTERNAL_SERVICE_ERROR",
        )


class ConfigurationException(BaseException):
    def __init__(self, message: str = "System configuration error"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=message,
            error_code="CONFIGURATION_ERROR",
        )
