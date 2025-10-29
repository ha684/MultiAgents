# src/infrastructure/storage/__init__.py
from src.core.config.settings import settings
from src.infrastructure.storage.minio_client import MinioClient

minio_client = MinioClient(
    endpoint=settings.minio_endpoint,
    access_key=settings.minio_access_key,
    secret_key=settings.minio_secret_key,
    secure=settings.minio_secure,
)
