# src/connector/__init__.py
from src.config import settings
from src.connector.minio_conn import MinioClient
from src.connector.database_conn import DatabaseConnection
from src.connector.redis_conn import Redis

database_connector = DatabaseConnection(
    db_url=settings.database_url,
)

minio_client = MinioClient(
    endpoint=settings.minio_endpoint,
    access_key=settings.minio_access_key,
    secret_key=settings.minio_secret_key,
    secure=settings.minio_secure,
)

redis_client = Redis()
