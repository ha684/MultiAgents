# src/infrastructure/cache/__init__.py
from src.core.config.settings import settings
from src.infrastructure.cache.redis_client import Redis

redis_client = Redis(uri=settings.redis_uri)
