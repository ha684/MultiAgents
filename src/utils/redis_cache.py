# src/utils/redis_cache.py

from typing import Optional, Any
import hashlib
import json
from pathlib import Path

from langchain_redis.cache import BaseCache, RETURN_VAL_TYPE
from langchain_core.load.dump import dumps
from langchain_core.load.load import loads

from src.event_pub.redis_client import get_redis


class RedisCache(BaseCache):
    """Redis cache implementation for LangChain.

    This class provides a Redis-based caching mechanism for LangChain, allowing
    storage and retrieval of language model responses.
    """

    def __init__(
        self,
        ttl: Optional[int] = None,
        prefix: Optional[str] = "redis",
    ):
        self.redis = None
        self.ttl = ttl
        self.prefix = prefix

    def _key(self, prompt: str, llm_string: str) -> str:
        """Create a key for the cache."""
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()
        llm_string_hash = hashlib.md5(llm_string.encode()).hexdigest()
        return f"{self.prefix}:{prompt_hash}:{llm_string_hash}"

    async def lookup(self, prompt: str, llm_string: str) -> Optional[RETURN_VAL_TYPE]:
        """Look up the result of a previous language model call in the Redis cache.

        This method checks if there's a cached result for the given prompt and language
        model combination.
        """
        if self.redis is None:
            self.redis = await get_redis()
        key = self._key(prompt, llm_string)
        result = await self.redis.json().get(key)
        if result:
            return [loads(json.dumps(result))]
        return None

    async def update(
        self, prompt: str, llm_string: str, return_val: RETURN_VAL_TYPE
    ) -> None:
        """Update the cache with a new result for a given prompt and language model.

        This method stores a new result in the Redis cache for the specified prompt and
        language model combination.
        """
        if self.redis is None:
            self.redis = await get_redis()
        key = self._key(prompt, llm_string)
        json_value = json.loads(dumps(return_val[0]))
        await self.redis.json().set(key, Path.root_path(), json_value)
        if self.ttl is not None:
            await self.redis.expire(key, self.ttl)

    async def clear(self, **kwargs: Any) -> None:
        """Clear all entries in the Redis cache that match the cache prefix.

        This method removes all cache entries that start with the specified prefix.
        """
        if self.redis is None:
            self.redis = await get_redis()
        cursor = 0
        pipe = await self.redis.pipeline()
        while True:
            try:
                cursor, keys = await self.redis.scan(
                    cursor, match=f"{self.prefix}:*", count=100
                )  # type: ignore[misc]
                if keys:
                    await pipe.delete(*keys)
                    await pipe.execute()

                if cursor == 0:
                    break
            finally:
                await pipe.reset()
