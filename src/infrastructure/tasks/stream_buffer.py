# src/infrastructure/tasks/stream_buffer.py
"""
Redis Stream Buffer for Chat Streaming

This module manages Redis Streams for real-time chat streaming with:
- Persistent message storage with automatic TTL
- Support for late subscribers (replay from beginning)
- Support for reconnection (resume from last_event_id)
- Task status and cancellation management
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncGenerator
from zoneinfo import ZoneInfo

from src.domain.schemas.chat_task import ChatTaskStatus
from src.infrastructure.cache import redis_client
from src.utils.decorators import singleton
from src.utils.logger_conf import logger


@dataclass
class StreamMessage:
    """Represents a message in the chat stream"""

    event_id: str
    event_type: str
    data: dict[str, Any]
    timestamp: str = field(
        default_factory=lambda: datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "data": self.data,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_redis(cls, event_id: str, data: dict[str, str]) -> "StreamMessage":
        """Create StreamMessage from Redis stream entry"""
        return cls(
            event_id=event_id,
            event_type=data.get("event_type", "unknown"),
            data=json.loads(data.get("data", "{}")),
            timestamp=data.get("timestamp", ""),
        )


@singleton
class ChatStreamBuffer:
    """
    Manages Redis Streams for chat message buffering.

    Redis Key Patterns:
    - chat:stream:{task_id}     - Stream containing all events
    - chat:status:{task_id}     - Task status (pending/streaming/complete/cancelled/error)
    - chat:cancel:{task_id}     - Cancellation flag
    - chat:meta:{task_id}       - Task metadata (conversation_id, user_id, etc.)

    Note: Final results are stored in PostgreSQL, not Redis.
    Redis is only used during streaming for real-time delivery and reconnection support.
    """

    STREAM_PREFIX = "chat:stream"
    STATUS_PREFIX = "chat:status"
    CANCEL_PREFIX = "chat:cancel"
    META_PREFIX = "chat:meta"

    STREAM_TTL = 300
    STATUS_TTL = 600
    META_TTL = 600
    CANCEL_TTL = 300

    def __init__(self):
        self.redis = redis_client

    def _stream_key(self, task_id: str) -> str:
        return f"{self.STREAM_PREFIX}:{task_id}"

    def _status_key(self, task_id: str) -> str:
        return f"{self.STATUS_PREFIX}:{task_id}"

    def _cancel_key(self, task_id: str) -> str:
        return f"{self.CANCEL_PREFIX}:{task_id}"

    def _meta_key(self, task_id: str) -> str:
        return f"{self.META_PREFIX}:{task_id}"

    async def init_task(
        self,
        task_id: str,
        conversation_id: str,
        user_id: str,
        kb_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """
        Initialize a new chat task with metadata.

        Args:
            task_id: Unique task identifier
            conversation_id: Associated conversation ID
            user_id: User who initiated the task
            kb_id: Knowledge base ID
            metadata: Additional metadata

        Returns:
            True if initialization successful
        """
        try:
            redis = self.redis.get()

            await redis.set(
                self._status_key(task_id),
                ChatTaskStatus.PENDING.value,
                ex=self.STATUS_TTL,
            )

            meta = {
                "task_id": task_id,
                "conversation_id": conversation_id,
                "user_id": user_id,
                "kb_id": kb_id,
                "created_at": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat(),
                **(metadata or {}),
            }
            await redis.set(
                self._meta_key(task_id),
                json.dumps(meta),
                ex=self.META_TTL,
            )

            logger.info(f"Initialized chat task: {task_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize chat task {task_id}: {e}")
            return False

    async def set_status(self, task_id: str, status: ChatTaskStatus) -> bool:
        """Set task status"""
        try:
            redis = self.redis.get()
            await redis.set(
                self._status_key(task_id),
                status.value,
                ex=self.STATUS_TTL,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to set status for task {task_id}: {e}")
            return False

    async def get_status(self, task_id: str) -> ChatTaskStatus | None:
        """Get task status"""
        try:
            redis = self.redis.get()
            status = await redis.get(self._status_key(task_id))
            return ChatTaskStatus(status) if status else None
        except Exception as e:
            logger.error(f"Failed to get status for task {task_id}: {e}")
            return None

    async def get_metadata(self, task_id: str) -> dict[str, Any] | None:
        """Get task metadata"""
        try:
            redis = self.redis.get()
            meta = await redis.get(self._meta_key(task_id))
            return json.loads(meta) if meta else None
        except Exception as e:
            logger.error(f"Failed to get metadata for task {task_id}: {e}")
            return None

    async def request_cancellation(self, task_id: str) -> bool:
        """Request task cancellation"""
        try:
            redis = self.redis.get()
            await redis.set(
                self._cancel_key(task_id),
                "1",
                ex=self.CANCEL_TTL,
            )
            await self.set_status(task_id, ChatTaskStatus.CANCELLED)
            logger.info(f"Cancellation requested for task: {task_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to request cancellation for task {task_id}: {e}")
            return False

    async def is_cancelled(self, task_id: str) -> bool:
        """Check if task is cancelled"""
        try:
            redis = self.redis.get()
            result = await redis.get(self._cancel_key(task_id))
            return result == "1"
        except Exception as e:
            logger.error(f"Failed to check cancellation for task {task_id}: {e}")
            return False

    async def publish_event(
        self,
        task_id: str,
        event_type: str,
        data: dict[str, Any],
    ) -> str | None:
        """
        Publish an event to the task's stream.

        Args:
            task_id: Task identifier
            event_type: Type of event (e.g., "content_delta", "status", "error")
            data: Event data

        Returns:
            Event ID if successful, None otherwise
        """
        try:
            redis = self.redis.get()
            stream_key = self._stream_key(task_id)

            message = StreamMessage(
                event_id="",
                event_type=event_type,
                data=data,
            )

            event_id = await redis.xadd(
                stream_key,
                {
                    "event_type": event_type,
                    "data": json.dumps(data, ensure_ascii=False),
                    "timestamp": message.timestamp,
                },
            )

            await redis.expire(stream_key, self.STREAM_TTL)

            return event_id

        except Exception as e:
            logger.error(f"Failed to publish event for task {task_id}: {e}")
            return None

    async def publish_content_delta(
        self,
        task_id: str,
        text: str,
        index: int,
        delta_type: str = "text_delta",
    ) -> str | None:
        """Publish a content delta event"""
        return await self.publish_event(
            task_id,
            "content_block_delta",
            {
                "delta": {"type": delta_type, "text": text},
                "index": index,
            },
        )

    async def publish_thinking_delta(
        self,
        task_id: str,
        text: str,
        index: int,
    ) -> str | None:
        """Publish a thinking delta event"""
        return await self.publish_content_delta(
            task_id,
            text,
            index,
            delta_type="thinking_delta",
        )

    async def publish_status(
        self,
        task_id: str,
        phase: str,
        message: str,
        progress: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Publish a status update event"""
        data = {"phase": phase, "message": message}
        if progress is not None:
            data["progress"] = min(max(progress, 0.0), 1.0)
        if metadata:
            data["metadata"] = metadata
        return await self.publish_event(task_id, "status", data)

    async def publish_error(
        self,
        task_id: str,
        error_type: str,
        message: str,
        code: int | None = None,
    ) -> str | None:
        """Publish an error event"""
        data = {"type": error_type, "message": message}
        if code:
            data["code"] = code
        return await self.publish_event(task_id, "error", data)

    async def publish_complete(
        self,
        task_id: str,
        references: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Publish completion event"""
        data = {}
        if references:
            data["references"] = references
        if metadata:
            data["metadata"] = metadata
        return await self.publish_event(task_id, "message_stop", data)

    async def read_all_events(self, task_id: str) -> list[StreamMessage]:
        """
        Read all events from a task's stream (for replay).

        Returns:
            List of all StreamMessages in order
        """
        try:
            redis = self.redis.get()
            stream_key = self._stream_key(task_id)

            entries = await redis.xrange(stream_key)

            messages = []
            for event_id, data in entries:
                messages.append(StreamMessage.from_redis(event_id, data))

            return messages

        except Exception as e:
            logger.error(f"Failed to read events for task {task_id}: {e}")
            return []

    async def read_events_from(
        self,
        task_id: str,
        last_event_id: str,
    ) -> list[StreamMessage]:
        """
        Read events after a specific event ID (for resume).

        Args:
            task_id: Task identifier
            last_event_id: Read events after this ID

        Returns:
            List of StreamMessages after the given ID
        """
        try:
            redis = self.redis.get()
            stream_key = self._stream_key(task_id)

            entries = await redis.xrange(stream_key, min=f"({last_event_id}")

            messages = []
            for event_id, data in entries:
                messages.append(StreamMessage.from_redis(event_id, data))

            return messages

        except Exception as e:
            logger.error(
                f"Failed to read events from {last_event_id} for task {task_id}: {e}"
            )
            return []

    async def subscribe_to_stream(
        self,
        task_id: str,
        last_event_id: str | None = None,
        block_timeout: int = 5000,
    ) -> AsyncGenerator[StreamMessage, None]:
        """
        Subscribe to a task's stream for real-time events.

        This will:
        1. Replay events from the beginning (or after last_event_id)
        2. Then block and wait for new events
        3. Exit when task completes or is cancelled

        Args:
            task_id: Task identifier
            last_event_id: Resume from this event ID (None = start from beginning)
            block_timeout: Timeout in ms for blocking read

        Yields:
            StreamMessage objects
        """
        redis = self.redis.get()
        stream_key = self._stream_key(task_id)

        if last_event_id:
            current_id = last_event_id
        else:
            current_id = "0"

        try:
            while True:
                status = await self.get_status(task_id)
                if status in (
                    ChatTaskStatus.COMPLETE,
                    ChatTaskStatus.CANCELLED,
                    ChatTaskStatus.ERROR,
                ):
                    remaining = await redis.xrange(stream_key, min=f"({current_id}")
                    for event_id, data in remaining:
                        yield StreamMessage.from_redis(event_id, data)
                        current_id = event_id
                    break

                result = await redis.xread(
                    {stream_key: current_id},
                    block=block_timeout,
                    count=100,
                )

                if not result:
                    continue

                for stream_name, entries in result:
                    for event_id, data in entries:
                        yield StreamMessage.from_redis(event_id, data)
                        current_id = event_id

        except Exception as e:
            logger.error(f"Error in stream subscription for task {task_id}: {e}")
            raise

    async def cleanup_task(self, task_id: str) -> bool:
        """Clean up all Redis keys for a task"""
        try:
            redis = self.redis.get()
            keys = [
                self._stream_key(task_id),
                self._status_key(task_id),
                self._cancel_key(task_id),
                self._meta_key(task_id),
            ]
            await redis.delete(*keys)
            logger.info(f"Cleaned up task: {task_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cleanup task {task_id}: {e}")
            return False


chat_stream_buffer = ChatStreamBuffer()
