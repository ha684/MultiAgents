# src/infrastructure/cache/redis_client.py
import hashlib
import json
import time
from datetime import datetime
from json import loads
from typing import Any
from zoneinfo import ZoneInfo

import redis.asyncio as aioredis
from langchain_core.caches import RETURN_VAL_TYPE, BaseCache
from langchain_core.load.dump import dumps
from redis.commands.json.path import Path as JSONPath

from src.utils.logger_conf import logger


class Redis(BaseCache):
    _client: aioredis.Redis | None = None

    def __init__(
        self,
        uri: str,
        ttl: int | None = 3600,
    ):
        self.ttl = ttl
        self._client = aioredis.from_url(uri, decode_responses=True)

    def get(self) -> aioredis.Redis:
        """Get the Redis client."""
        assert self._client is not None, "Redis not initialized"
        return self._client

    async def connect(self):
        """
        Establishes a connection to the Redis server.
        """
        try:
            await self._client.ping()
            logger.info("Redis: Successfully connected to Redis.")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Redis: {e}")

    async def close(self):
        """Close the Redis client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _key(self, prefix: str, *parts: str) -> str:
        hashed = [hashlib.md5(p.encode()).hexdigest() for p in parts]
        return f"{prefix}:" + ":".join(hashed)

    async def get_obj(self, prefix: str, *parts: str):
        key = self._key(prefix, *parts)
        return await self.get().json().get(key)

    async def set_obj(
        self, prefix: str, value: Any, *parts: str, ttl: int | None = None
    ):
        json_value = json.loads(dumps(value))
        key = self._key(prefix, *parts)
        await self.get().json().set(key, JSONPath.root_path(), json_value)
        await self.get().expire(key, ttl if ttl is not None else self.ttl)

    async def del_key(self, prefix: str, *parts: str):
        key = self._key(prefix, *parts)
        await self.get().delete(key)

    async def lookup(self, prompt: str, llm_string: str) -> RETURN_VAL_TYPE | None:
        """Look up the result of a previous language model call in the Redis cache.

        This method checks if there's a cached result for the given prompt and language
        model combination.
        """
        prefix = "llm_cache"
        result = await self.get_obj(prefix, prompt, llm_string)
        if result:
            return [loads(json.dumps(result))]
        return None

    async def alookup(self, prompt: str, llm_string: str) -> RETURN_VAL_TYPE | None:
        return await self.lookup(prompt, llm_string)

    async def update(
        self, prompt: str, llm_string: str, return_val: RETURN_VAL_TYPE
    ) -> None:
        """Update the cache with a new result for a given prompt and language model.

        This method stores a new result in the Redis cache for the specified prompt and
        language model combination.
        """
        prefix = "llm_cache"
        await self.set_obj(prefix, return_val[0], prompt, llm_string, ttl=self.ttl)

    async def aupdate(
        self, prompt: str, llm_string: str, return_val: RETURN_VAL_TYPE
    ) -> None:
        return await self.update(prompt, llm_string, return_val)

    async def rate_limit(
        self, key: str, limit: int, window_seconds: int
    ) -> tuple[bool, dict[str, Any]]:
        """
        Check if request is allowed under rate limit using Redis

        This uses a sliding window approach with Redis sorted sets
        """
        now = time.time()
        prefix = "rate_limit"
        redis_key = self._key(prefix, key)
        redis = self.get()
        pipe = redis.pipeline()

        try:
            await pipe.zremrangebyscore(redis_key, 0, now - window_seconds)

            await pipe.zcard(redis_key)

            results = await pipe.execute()
            current_count = results[1]

            if current_count >= limit:
                oldest_requests = await redis.zrange(redis_key, 0, 0, withscores=True)
                if oldest_requests:
                    oldest_time = oldest_requests[0][1]
                    retry_after = int(window_seconds - (now - oldest_time)) + 1
                else:
                    retry_after = window_seconds

                return False, {
                    "limit": limit,
                    "remaining": 0,
                    "reset_time": (
                        datetime.fromtimestamp(
                            oldest_time + window_seconds,
                            tz=ZoneInfo("Asia/Ho_Chi_Minh"),
                        )
                        if oldest_requests
                        else datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
                    ),
                    "retry_after": retry_after,
                }
            unique_score = now + (time.time_ns() % 1000000) / 1000000000
            await redis.zadd(redis_key, {str(unique_score): unique_score})
            await redis.expire(redis_key, window_seconds + 1)
            oldest_requests = await redis.zrange(redis_key, 0, 0, withscores=True)
            reset_time = (
                datetime.fromtimestamp(
                    oldest_requests[0][1] + window_seconds,
                    tz=ZoneInfo("Asia/Ho_Chi_Minh"),
                )
                if oldest_requests
                else datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
            )

            return True, {
                "limit": limit,
                "remaining": limit - (current_count + 1),
                "reset_time": reset_time,
                "retry_after": None,
            }

        except aioredis.RedisError as e:
            raise Exception(f"Redis rate limiter error: {e}")

    async def clear(self, prefix: str) -> None:
        """Clear all entries in the Redis cache that match the cache prefix.

        This method removes all cache entries that start with the specified prefix.
        """
        redis = self.get()
        cursor = 0
        pipe = redis.pipeline()
        while True:
            try:
                cursor, keys = await redis.scan(cursor, match=f"{prefix}:*", count=100)  # type: ignore[misc]
                if keys:
                    await pipe.delete(*keys)
                    await pipe.execute()

                if cursor == 0:
                    break
            finally:
                await pipe.reset()
