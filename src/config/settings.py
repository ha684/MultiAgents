import os
from typing import Optional
from pydantic import field_validator, ValidationInfo
from pydantic_settings import BaseSettings, SettingsConfigDict
from datetime import timedelta
from src.models.chat import SearchProvider


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

    google_client_id: Optional[str] = os.getenv("GOOGLE_CLIENT_ID")
    google_client_secret: Optional[str] = os.getenv("GOOGLE_CLIENT_SECRET")
    google_refresh_token: Optional[str] = os.getenv("GOOGLE_REFRESH_TOKEN")

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


if __name__ == "__main__":
    print(settings.model_dump_json(indent=2, exclude_none=True))
    print(settings.model_dump(exclude_none=True))
