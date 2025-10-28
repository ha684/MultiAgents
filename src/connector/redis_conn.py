# src/event_pub/redis_client.py
import redis.asyncio as redis
from src.config.settings import settings


class RedisClient:
    client: redis.Redis | None = None

    @classmethod
    def _initialize(cls):
        """A private class method to run the init logic once."""
        uri = settings.redis_uri

        cls.client = redis.from_url(
            uri,
            decode_responses=True,
        )

    @classmethod
    def get_client(cls) -> redis.Redis:
        if cls.client is None:
            cls._initialize()

        return cls.client


redis_client = RedisClient.get_client()
