# src/core/config/settings.py
from datetime import timedelta
import os
from typing import List, Optional

from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.domain.schemas.chat import SearchProvider


class Settings(BaseSettings):
    # MinIO configuration
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str
    minio_secure: bool = True

    # Redis configuration
    redis_uri: str

    # Database configuration
    database_url: str

    # Vector storage (Qdrant) configuration
    vector_storage_url: str = "localhost:6333"
    vector_collection_name: str = "kms_vector_store"

    # Neo4j configuration
    neo4j_uri: str = "neo4j://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"

    # ReRank API configuration
    rerank_url: str
    rerank_api_key: str

    # Text Embeddings configuration
    text_embedding_url: str
    text_embedding_api_key: str
    text_embedding_model: str
    embedding_dimensions: int = 1024

    ntqai_base_url: str
    ntqai_api_key: str
    ntqai_model: str

    # Websearch configuration
    enable_websearch: bool = False
    websearch_provider: Optional[str] = None
    tavily_api_key: Optional[str] = None
    firecrawl_api_url: Optional[str] = None
    firecrawl_api_key: Optional[str] = None

    openai_api_key: Optional[str] = None
    openai_model_name: Optional[str] = None

    # File storage configuration
    temp_dir: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tmp")

    # images to text config
    minio_presigned_url_expiration: timedelta = timedelta(hours=10)

    port: int = 8000

    # JWT config
    jwt_secret_key: str = "123"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    jwt_issuer: str = "knowledge-management-system"

    # Account Security
    max_login_attempts: int = 5
    account_lockout_duration_minutes: int = 15
    session_expire_hours: int = 24

    # OAuth Configuration
    google_client_id: Optional[str] = os.getenv("GOOGLE_CLIENT_ID")
    google_client_secret: Optional[str] = os.getenv("GOOGLE_CLIENT_SECRET")
    google_refresh_token: Optional[str] = os.getenv("GOOGLE_REFRESH_TOKEN")

    github_client_id: Optional[str] = os.getenv("GITHUB_CLIENT_ID")
    github_client_secret: Optional[str] = os.getenv("GITHUB_CLIENT_SECRET")

    oauth_redirect_url: str = "http://localhost:8000/auth/oauth/callback"
    google_scopes: List[str] = ["https://www.googleapis.com/auth/gmail.send"]
    frontend_url: str = "http://localhost:3000"

    # Rate Limiting
    rate_limit_requests: int = 100
    rate_limit_window_minutes: int = 1
    login_rate_limit_requests: int = 5
    login_rate_limit_window_minutes: int = 15

    # CORS Configuration
    cors_allow_origins: List[str] = ["*"]
    cors_allow_credentials: bool = True
    cors_allow_methods: List[str] = ["*"]
    cors_allow_headers: List[str] = ["*"]

    email_verification_token_expire_minutes: int = 10
    password_reset_token_expire_hours: int = 1

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    celery_worker_num: int = 3
    rerank_model: Optional[str] = "nx-text-rerank-001"
    cache_dir: str = "./.cache"

    @field_validator("websearch_provider")
    @classmethod
    def validate_websearch_provider(
        cls, v: Optional[SearchProvider], info: ValidationInfo
    ) -> Optional[SearchProvider]:
        """Validate that websearch provider is set when websearch is enabled."""
        if info.data.get("enable_websearch", False) and v is None:
            raise ValueError(
                "websearch_provider must be specified when enable_websearch is True"
            )
        return v

    @field_validator("tavily_api_key")
    @classmethod
    def validate_tavily_api_key(
        cls, v: Optional[str], info: ValidationInfo
    ) -> Optional[str]:
        """Validate that Tavily API key is provided when Tavily is selected as provider."""
        if (
            info.data.get("enable_websearch", False)
            and info.data.get("websearch_provider") == SearchProvider.TAVILY
            and not v
        ):
            raise ValueError(
                "tavily_api_key is required when websearch_provider is set to 'tavily'"
            )
        return v

    @field_validator("firecrawl_api_key")
    @classmethod
    def validate_firecrawl_api_key(
        cls, v: Optional[str], info: ValidationInfo
    ) -> Optional[str]:
        """Validate that Firecrawl API key is provided when Firecrawl is selected as provider."""
        if (
            info.data.get("enable_websearch", False)
            and info.data.get("websearch_provider") == SearchProvider.FIRECRAWL
            and not v
        ):
            raise ValueError(
                "firecrawl_api_key is required when websearch_provider is set to 'firecrawl'"
            )
        return v

    @field_validator("firecrawl_api_url")
    @classmethod
    def validate_firecrawl_api_url(
        cls, v: Optional[str], info: ValidationInfo
    ) -> Optional[str]:
        """Validate that Firecrawl API URL is provided when Firecrawl is selected as provider."""
        if (
            info.data.get("enable_websearch", False)
            and info.data.get("websearch_provider") == SearchProvider.FIRECRAWL
            and not v
        ):
            raise ValueError(
                "firecrawl_api_url is required when websearch_provider is set to 'firecrawl'"
            )
        return v


settings = Settings.model_validate({})


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
        "requests": settings.rate_limit_requests,
        "window": timedelta(minutes=settings.rate_limit_window_minutes),
    },
    "auth": {
        "requests": settings.login_rate_limit_requests,
        "window": timedelta(minutes=settings.login_rate_limit_window_minutes),
    },
    "password_reset": {"requests": 3, "window": timedelta(hours=1)},
}
