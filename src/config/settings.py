import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from datetime import timedelta


class Settings(BaseSettings):
    # MinIO configuration
    minio_endpoint: str = None
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str
    minio_secure: bool = False

    # Redis configuration
    redis_uri: str

    # Database configuration
    database_url: str
    database_pool_pre_ping: bool = True
    database_pool_size: int = 100
    database_max_overflow: int = 200
    database_pool_timeout: int = 30
    database_pool_recycle: int = 1800
    database_echo: bool = False
    database_statement_timeout: int = 30000
    database_ssl_required: bool = False
    database_auto_create_tables: bool = True

    # Vector storage (Qdrant) configuration
    vector_storage_url: str = "http://qdrant:6333"
    vector_collection_name: str = "kms_collection_1024"

    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "123456"

    # ReRank API configuration
    rerank_url: str
    rerank_api_key: str
    rerank_model: Optional[str] = "nx-text-rerank-001"

    # Text Embeddings configuration
    text_embedding_url: str
    text_embedding_api_key: str
    text_embedding_model: str
    embedding_dimensions: int = 1024

    ntqai_base_url: str = ""
    ntqai_api_key: str = ""
    ntqai_model: str = "nxchat"
    temperature: float = 0
    openai_api_key: Optional[str] = None
    openai_model_name: Optional[str] = None

    google_api_key: Optional[str] = None
    google_api_model: Optional[str] = None
    firecrawl_api_url: Optional[str] = None
    # File storage configuration
    temp_dir: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tmp")

    # images to text config
    minio_presigned_url_expiration: timedelta = timedelta(hours=10)

    port: int = 8000

    # Default max key length
    DEFAULT_MAX_KEY_LENGTH: int = 255

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    celery_worker_num: int = 3

    def get_database_url_with_ssl(self) -> str:
        """Get database URL with SSL parameters if required"""
        if not self.database_ssl_required:
            return self.database_url

        if "postgresql" in self.database_url:
            separator = "&" if "?" in self.database_url else "?"
            return f"{self.database_url}{separator}sslmode=require"

        return self.database_url


settings = Settings()

if __name__ == "__main__":
    print(settings.model_dump_json(indent=2, exclude_none=True))
