# src/event_pub/redis_client.py
import redis.asyncio as aioredis
from src.config.settings import settings
from typing import Optional


class RedisClient:
    """Async Redis client manager"""

    _client: Optional[aioredis.Redis] = None

    @classmethod
    async def get_client(cls) -> aioredis.Redis:
        """
        Get or create Redis client (lazy initialization)
        Được gọi trong event loop context
        """
        if cls._client is None:
            cls._client = aioredis.from_url(
                settings.redis_uri,
                decode_responses=True,
                max_connections=50,
                socket_connect_timeout=5,
                socket_keepalive=True,
            )
        return cls._client


async def get_redis() -> aioredis.Redis:
    """
    Dependency function cho FastAPI
    Usage: redis: Redis = Depends(get_redis)
    """
    redis_client = await RedisClient.get_client()
    return redis_client
