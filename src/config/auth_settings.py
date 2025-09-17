# src/config/auth_settings.py
from pydantic_settings import BaseSettings
from typing import Optional, List
import os
from datetime import timedelta


class AuthSettings(BaseSettings):
    """Authentication and security settings"""

    # JWT Configuration
    jwt_secret_key: str = os.getenv(
        "JWT_SECRET_KEY", "your-super-secret-jwt-key-change-in-production"
    )
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    jwt_issuer: str = "knowledge-management-system"

    # Password Configuration
    password_hash_algorithm: str = "bcrypt"
    password_reset_token_expire_hours: int = 24
    email_verification_token_expire_minutes: int = 48

    # Account Security
    max_login_attempts: int = 5
    account_lockout_duration_minutes: int = 15
    session_expire_hours: int = 24

    # OAuth Configuration
    google_client_id: Optional[str] = os.getenv("GOOGLE_CLIENT_ID")
    google_client_secret: Optional[str] = os.getenv("GOOGLE_CLIENT_SECRET")
    github_client_id: Optional[str] = os.getenv("GITHUB_CLIENT_ID")
    github_client_secret: Optional[str] = os.getenv("GITHUB_CLIENT_SECRET")
    oauth_redirect_url: str = "http://localhost:8000/auth/oauth/callback"

    # Rate Limiting
    rate_limit_requests: int = 100
    rate_limit_window_minutes: int = 1
    login_rate_limit_requests: int = 5
    login_rate_limit_window_minutes: int = 15

    # CORS Configuration
    cors_allow_origins: List[str] = ["http://localhost:3000", "http://localhost:8080"]
    cors_allow_credentials: bool = True
    cors_allow_methods: List[str] = ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"]
    cors_allow_headers: List[str] = ["*"]

    # Security Headers
    security_headers_enabled: bool = True
    hsts_max_age: int = 31536000  # 1 year

    # Email Configuration (for password reset and verification)
    smtp_host: Optional[str] = os.getenv("SMTP_HOST", "localhost")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: Optional[str] = os.getenv("SMTP_USERNAME")
    smtp_password: Optional[str] = os.getenv("SMTP_PASSWORD")
    smtp_use_tls: bool = True
    email_from: str = os.getenv("EMAIL_FROM", "noreply@yourdomain.com")

    # Application URLs
    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
    api_base_url: str = os.getenv("API_BASE_URL", "http://localhost:8000")

    # Database
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+asyncpg://user:password@localhost/dbname"
    )

    # Redis (for session storage and rate limiting)
    redis_url: Optional[str] = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Development/Debug
    debug: bool = os.getenv("DEBUG", "False").lower() == "true"
    testing: bool = os.getenv("TESTING", "False").lower() == "true"

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


# Create global settings instance
auth_settings = AuthSettings()

# Role-based permissions mapping
ROLE_PERMISSIONS = {
    "admin": [
        "user:read",
        "user:write",
        "user:delete",
        "user:manage",
        "document:read",
        "document:write",
        "document:delete",
        "document:manage",
        "chat:read",
        "chat:write",
        "chat:delete",
        "chat:manage",
        "knowledge_base:read",
        "knowledge_base:write",
        "knowledge_base:delete",
        "knowledge_base:manage",
        "system:read",
        "system:write",
        "system:manage",
    ],
    "moderator": [
        "user:read",
        "document:read",
        "document:write",
        "document:manage",
        "chat:read",
        "chat:write",
        "chat:manage",
        "knowledge_base:read",
        "knowledge_base:write",
        "knowledge_base:manage",
    ],
    "user": [
        "document:read",
        "document:write",
        "chat:read",
        "chat:write",
        "knowledge_base:read",
    ],
}

# Default system permissions
DEFAULT_PERMISSIONS = [
    # User permissions
    {
        "name": "user:read",
        "description": "Read user information",
        "resource": "user",
        "action": "read",
    },
    {
        "name": "user:write",
        "description": "Update user information",
        "resource": "user",
        "action": "write",
    },
    {
        "name": "user:delete",
        "description": "Delete users",
        "resource": "user",
        "action": "delete",
    },
    {
        "name": "user:manage",
        "description": "Manage user accounts",
        "resource": "user",
        "action": "manage",
    },
    # Document permissions
    {
        "name": "document:read",
        "description": "Read documents",
        "resource": "document",
        "action": "read",
    },
    {
        "name": "document:write",
        "description": "Create/update documents",
        "resource": "document",
        "action": "write",
    },
    {
        "name": "document:delete",
        "description": "Delete documents",
        "resource": "document",
        "action": "delete",
    },
    {
        "name": "document:manage",
        "description": "Manage document settings",
        "resource": "document",
        "action": "manage",
    },
    # Chat permissions
    {
        "name": "chat:read",
        "description": "Read chat conversations",
        "resource": "chat",
        "action": "read",
    },
    {
        "name": "chat:write",
        "description": "Send chat messages",
        "resource": "chat",
        "action": "write",
    },
    {
        "name": "chat:delete",
        "description": "Delete chat conversations",
        "resource": "chat",
        "action": "delete",
    },
    {
        "name": "chat:manage",
        "description": "Manage chat settings",
        "resource": "chat",
        "action": "manage",
    },
    # Knowledge base permissions
    {
        "name": "knowledge_base:read",
        "description": "Read knowledge bases",
        "resource": "knowledge_base",
        "action": "read",
    },
    {
        "name": "knowledge_base:write",
        "description": "Create/update knowledge bases",
        "resource": "knowledge_base",
        "action": "write",
    },
    {
        "name": "knowledge_base:delete",
        "description": "Delete knowledge bases",
        "resource": "knowledge_base",
        "action": "delete",
    },
    {
        "name": "knowledge_base:manage",
        "description": "Manage knowledge base settings",
        "resource": "knowledge_base",
        "action": "manage",
    },
    # System permissions
    {
        "name": "system:read",
        "description": "Read system information",
        "resource": "system",
        "action": "read",
    },
    {
        "name": "system:write",
        "description": "Update system settings",
        "resource": "system",
        "action": "write",
    },
    {
        "name": "system:manage",
        "description": "Full system administration",
        "resource": "system",
        "action": "manage",
    },
]

# Rate limiting configuration
RATE_LIMIT_CONFIG = {
    "default": {
        "requests": auth_settings.rate_limit_requests,
        "window": timedelta(minutes=auth_settings.rate_limit_window_minutes),
    },
    "auth": {
        "requests": auth_settings.login_rate_limit_requests,
        "window": timedelta(minutes=auth_settings.login_rate_limit_window_minutes),
    },
    "password_reset": {"requests": 3, "window": timedelta(hours=1)},
}
