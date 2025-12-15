# src/infrastructure/kafka/redis_index_store.py
"""
Redis-based stream index store for production use.

This provides persistence across restarts and supports multiple instances.
"""

import json
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from src.infrastructure.cache import redis_client
from src.utils.logger_conf import logger


class RedisStreamIndexStore:
    """
    Redis-backed store for stream index information.

    Stores request_id -> StreamIndexInfo mappings in Redis for:
    - Persistence across restarts
    - Shared state across multiple FastAPI instances
    - Automatic expiry via TTL
    """

    PREFIX = "stream_index"
    DEFAULT_TTL = 86400  # 24 hours

    def __init__(self, ttl: int = DEFAULT_TTL):
        self.ttl = ttl
        self._redis = redis_client.get()

    def _key(self, request_id: str) -> str:
        """Generate Redis key for a request_id."""
        return f"{self.PREFIX}:{request_id}"

    async def set(
        self,
        request_id: str,
        partition: int,
        offset: int,
        status: str = "running",
    ) -> None:
        """Set or update stream index info."""
        key = self._key(request_id)

        # Check if exists to preserve start_offset
        existing = await self.get(request_id)

        if existing:
            data = {
                "partition": partition,
                "start_offset": existing.get("start_offset", offset),
                "last_offset": offset,
                "status": status,
                "created_at": existing.get(
                    "created_at", datetime.now(ZoneInfo("UTC")).isoformat()
                ),
                "updated_at": datetime.now(ZoneInfo("UTC")).isoformat(),
            }
        else:
            data = {
                "partition": partition,
                "start_offset": offset,
                "last_offset": offset,
                "status": status,
                "created_at": datetime.now(ZoneInfo("UTC")).isoformat(),
                "updated_at": datetime.now(ZoneInfo("UTC")).isoformat(),
            }

        await self._redis.setex(key, self.ttl, json.dumps(data))

    async def get(self, request_id: str) -> Optional[dict[str, Any]]:
        """Get stream index info."""
        key = self._key(request_id)
        data = await self._redis.get(key)

        if data:
            return json.loads(data)
        return None

    async def delete(self, request_id: str) -> None:
        """Delete stream index info."""
        key = self._key(request_id)
        await self._redis.delete(key)

    async def exists(self, request_id: str) -> bool:
        """Check if stream index exists."""
        key = self._key(request_id)
        return await self._redis.exists(key) > 0

    async def update_status(self, request_id: str, status: str) -> None:
        """Update only the status field."""
        existing = await self.get(request_id)
        if existing:
            existing["status"] = status
            existing["updated_at"] = datetime.now(ZoneInfo("UTC")).isoformat()
            key = self._key(request_id)
            await self._redis.setex(key, self.ttl, json.dumps(existing))

    async def get_all_active(self) -> list[tuple[str, dict[str, Any]]]:
        """Get all active (running) streams."""
        cursor = 0
        results = []

        while True:
            cursor, keys = await self._redis.scan(
                cursor,
                match=f"{self.PREFIX}:*",
                count=100,
            )

            for key in keys:
                data = await self._redis.get(key)
                if data:
                    info = json.loads(data)
                    if info.get("status") == "running":
                        request_id = key.decode().split(":")[-1]
                        results.append((request_id, info))

            if cursor == 0:
                break

        return results


# Create a wrapper that can use either in-memory or Redis store
class HybridStreamIndexStore:
    """
    Hybrid store that uses Redis when available, falls back to in-memory.
    """

    def __init__(self):
        self._redis_store: Optional[RedisStreamIndexStore] = None
        self._memory_store: dict[str, dict[str, Any]] = {}
        self._redis_available = False

    async def _get_redis_store(self) -> Optional[RedisStreamIndexStore]:
        """Get Redis store, testing connection."""
        if self._redis_store is not None:
            return self._redis_store if self._redis_available else None

        try:
            store = RedisStreamIndexStore()
            await store._redis.ping()
            self._redis_store = store
            self._redis_available = True
            logger.info("Using Redis-backed stream index store")
            return store
        except Exception as e:
            logger.warning(
                f"Redis not available for stream index store, using in-memory: {e}"
            )
            self._redis_available = False
            return None

    async def set(
        self,
        request_id: str,
        partition: int,
        offset: int,
        status: str = "running",
    ) -> None:
        """Set or update stream index info."""
        redis_store = await self._get_redis_store()

        if redis_store:
            await redis_store.set(request_id, partition, offset, status)
        else:
            # In-memory fallback
            if request_id in self._memory_store:
                self._memory_store[request_id].update(
                    {
                        "last_offset": offset,
                        "status": status,
                    }
                )
            else:
                self._memory_store[request_id] = {
                    "partition": partition,
                    "start_offset": offset,
                    "last_offset": offset,
                    "status": status,
                    "created_at": datetime.now(ZoneInfo("UTC")),
                }

    async def get(self, request_id: str) -> Optional[dict[str, Any]]:
        """Get stream index info."""
        redis_store = await self._get_redis_store()

        if redis_store:
            return await redis_store.get(request_id)
        else:
            return self._memory_store.get(request_id)

    async def delete(self, request_id: str) -> None:
        """Delete stream index info."""
        redis_store = await self._get_redis_store()

        if redis_store:
            await redis_store.delete(request_id)
        else:
            self._memory_store.pop(request_id, None)


# Global hybrid store instance
hybrid_stream_index_store = HybridStreamIndexStore()
