from src.config import settings
from .minio_conn import MinioClient
from .database_conn import DatabaseConnection

database_connector = DatabaseConnection(
    db_url=settings.database_url,
)

minio_client = MinioClient(
    endpoint=settings.minio_endpoint,
    access_key=settings.minio_access_key,
    secret_key=settings.minio_secret_key,
    secure=settings.minio_secure,
)
