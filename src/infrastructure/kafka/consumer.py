# src/infrastructure/kafka/consumer.py
"""Kafka consumer for LLM streaming events."""

import asyncio
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncGenerator, Optional
from zoneinfo import ZoneInfo

from aiokafka import AIOKafkaConsumer, TopicPartition

from src.core.config.settings import settings
from src.infrastructure.kafka.schemas import (
    DeltaMessage,
    DoneMessage,
    ErrorMessage,
    KafkaMessage,
    KafkaMessageType,
    MetaMessage,
    StreamIndex,
)
from src.utils.logger_conf import logger


@dataclass
class StreamIndexInfo:
    """Information about a stream's Kafka index."""

    partition: int
    start_offset: int
    last_offset: int
    status: str = "running"
    created_at: datetime = field(default_factory=lambda: datetime.now(ZoneInfo("UTC")))

    def to_dict(self) -> dict[str, Any]:
        return {
            "partition": self.partition,
            "start_offset": self.start_offset,
            "last_offset": self.last_offset,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }


class StreamIndexStore:
    """
    In-memory store for stream index information.
    Maps request_id -> StreamIndexInfo for fast lookups.

    Note: For production with multiple instances, replace with Redis-based store.
    """

    def __init__(self):
        self._store: dict[str, StreamIndexInfo] = {}
        self._lock = asyncio.Lock()

    async def set(
        self,
        request_id: str,
        partition: int,
        offset: int,
        status: str = "running",
    ) -> None:
        """Set or update stream index info."""
        async with self._lock:
            if request_id in self._store:
                info = self._store[request_id]
                info.last_offset = offset
                info.status = status
            else:
                self._store[request_id] = StreamIndexInfo(
                    partition=partition,
                    start_offset=offset,
                    last_offset=offset,
                    status=status,
                )

    async def get(self, request_id: str) -> Optional[StreamIndexInfo]:
        """Get stream index info."""
        return self._store.get(request_id)

    async def delete(self, request_id: str) -> None:
        """Delete stream index info."""
        async with self._lock:
            self._store.pop(request_id, None)

    async def cleanup_old_entries(self, max_age_hours: int = 24) -> int:
        """Remove entries older than max_age_hours."""
        now = datetime.now(ZoneInfo("UTC"))
        count = 0
        async with self._lock:
            to_delete = []
            for request_id, info in self._store.items():
                age = (now - info.created_at).total_seconds() / 3600
                if age > max_age_hours:
                    to_delete.append(request_id)
            for request_id in to_delete:
                del self._store[request_id]
                count += 1
        return count


# Global index store (in-memory, for simple deployments)
stream_index_store = StreamIndexStore()

# For production, import and use the hybrid store:
# from src.infrastructure.kafka.redis_index_store import hybrid_stream_index_store as stream_index_store


def parse_kafka_message(data: dict[str, Any]) -> KafkaMessage:
    """Parse raw Kafka message data into typed message."""
    msg_type = data.get("type", "")

    if msg_type == KafkaMessageType.DELTA.value:
        return DeltaMessage(**data)
    elif msg_type == KafkaMessageType.META.value:
        return MetaMessage(**data)
    elif msg_type == KafkaMessageType.DONE.value:
        return DoneMessage(**data)
    elif msg_type == KafkaMessageType.ERROR.value:
        return ErrorMessage(**data)
    else:
        raise ValueError(f"Unknown message type: {msg_type}")


class KafkaConsumerManager:
    """
    Manages Kafka consumers for LLM streaming events.

    Provides two modes:
    1. Background consumer: Continuously consumes and routes messages to subscribers
    2. Catch-up consumer: Seeks to a specific offset and replays messages
    """

    _instance: Optional["KafkaConsumerManager"] = None

    def __new__(cls) -> "KafkaConsumerManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self._topic = settings.kafka_topic_llm_responses
        self._bootstrap_servers = settings.kafka_bootstrap_servers
        self._security_protocol = settings.kafka_security_protocol

        # Subscribers by request_id
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._subscriber_lock = asyncio.Lock()

        # Background consumer task
        self._consumer_task: Optional[asyncio.Task] = None
        self._running = False

    async def start_background_consumer(self) -> None:
        """Start the background consumer that routes messages to subscribers."""
        if self._running:
            return

        self._running = True
        self._consumer_task = asyncio.create_task(self._consume_loop())
        logger.info("Started Kafka background consumer")

    async def stop_background_consumer(self) -> None:
        """Stop the background consumer."""
        self._running = False
        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
            self._consumer_task = None
        logger.info("Stopped Kafka background consumer")

    async def _consume_loop(self) -> None:
        """Background loop that consumes and routes messages."""
        consumer = AIOKafkaConsumer(
            self._topic,
            bootstrap_servers=self._bootstrap_servers,
            security_protocol=self._security_protocol,
            group_id="llm-streaming-gateway",
            auto_offset_reset="latest",
            enable_auto_commit=True,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        )

        try:
            await consumer.start()
            logger.info(f"Kafka consumer connected to {self._bootstrap_servers}")

            while self._running:
                try:
                    # Poll with timeout to allow checking _running flag
                    messages = await consumer.getmany(timeout_ms=100, max_records=100)

                    for tp, records in messages.items():
                        for record in records:
                            await self._handle_message(record)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error in Kafka consume loop: {e}")
                    await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Fatal error in Kafka consumer: {e}")
        finally:
            await consumer.stop()

    async def _handle_message(self, record: Any) -> None:
        """Handle a single Kafka message and route to subscribers."""
        try:
            data = record.value
            request_id = data.get("request_id", "")

            if not request_id:
                logger.warning(f"Received message without request_id: {data}")
                return

            # Update index store
            await stream_index_store.set(
                request_id=request_id,
                partition=record.partition,
                offset=record.offset,
                status="done" if data.get("type") in ["done", "error"] else "running",
            )

            # Parse message
            message = parse_kafka_message(data)

            # Create cursor
            cursor = StreamIndex(partition=record.partition, offset=record.offset)

            # Route to subscribers
            async with self._subscriber_lock:
                queues = self._subscribers.get(request_id, [])
                for queue in queues:
                    try:
                        # Use non-blocking put with overflow handling
                        if queue.full():
                            # Drop oldest message on overflow (backpressure)
                            try:
                                queue.get_nowait()
                            except asyncio.QueueEmpty:
                                pass
                        queue.put_nowait((message, cursor))
                    except Exception as e:
                        logger.warning(
                            f"Failed to enqueue message for {request_id}: {e}"
                        )

        except Exception as e:
            logger.error(f"Error handling Kafka message: {e}")

    async def subscribe(
        self,
        request_id: str,
        queue_size: int = 1000,
    ) -> asyncio.Queue:
        """
        Subscribe to messages for a specific request_id.

        Returns a queue that will receive (message, cursor) tuples.
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=queue_size)

        async with self._subscriber_lock:
            self._subscribers[request_id].append(queue)

        logger.debug(f"Added subscriber for request_id={request_id}")
        return queue

    async def unsubscribe(self, request_id: str, queue: asyncio.Queue) -> None:
        """Unsubscribe from messages for a request_id."""
        async with self._subscriber_lock:
            if request_id in self._subscribers:
                try:
                    self._subscribers[request_id].remove(queue)
                    if not self._subscribers[request_id]:
                        del self._subscribers[request_id]
                except ValueError:
                    pass

        logger.debug(f"Removed subscriber for request_id={request_id}")

    async def replay_from_cursor(
        self,
        request_id: str,
        cursor: Optional[StreamIndex] = None,
        timeout_seconds: float = 300,
    ) -> AsyncGenerator[tuple[KafkaMessage, StreamIndex], None]:
        """
        Replay messages for a request_id starting from a cursor.

        If cursor is None, starts from the beginning of the request's stream.
        Yields (message, cursor) tuples.
        Stops when a terminal message (done/error) is received or timeout.
        """
        # Get index info for the request
        index_info = await stream_index_store.get(request_id)

        if cursor is None:
            if index_info is None:
                logger.warning(f"No index info found for request_id={request_id}")
                return
            # Start from the beginning
            partition = index_info.partition
            start_offset = index_info.start_offset
        else:
            partition = cursor.partition
            start_offset = cursor.offset + 1  # Start after the cursor

        # Create a dedicated consumer for replay
        consumer = AIOKafkaConsumer(
            bootstrap_servers=self._bootstrap_servers,
            security_protocol=self._security_protocol,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        )

        try:
            await consumer.start()

            # Assign to specific partition
            tp = TopicPartition(self._topic, partition)
            consumer.assign([tp])

            # Seek to the start offset
            consumer.seek(tp, start_offset)

            logger.debug(
                f"Starting replay for request_id={request_id} "
                f"from partition={partition}, offset={start_offset}"
            )

            start_time = asyncio.get_event_loop().time()

            while True:
                # Check timeout
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout_seconds:
                    logger.warning(f"Replay timeout for request_id={request_id}")
                    break

                # Poll for messages
                messages = await consumer.getmany(
                    timeout_ms=1000,
                    max_records=100,
                )

                for tp, records in messages.items():
                    for record in records:
                        data = record.value
                        msg_request_id = data.get("request_id", "")

                        # Filter by request_id (in case of partition key collisions)
                        if msg_request_id != request_id:
                            continue

                        message = parse_kafka_message(data)
                        cursor = StreamIndex(
                            partition=record.partition, offset=record.offset
                        )

                        yield message, cursor

                        # Check for terminal message
                        if isinstance(message, (DoneMessage, ErrorMessage)):
                            return

                # Check if we've caught up to the last known offset
                if index_info and index_info.status in ["done", "error"]:
                    # Already complete, no more messages expected
                    break

        except Exception as e:
            logger.error(f"Error during replay for request_id={request_id}: {e}")
            raise
        finally:
            await consumer.stop()


# Global consumer instance
_consumer_manager: Optional[KafkaConsumerManager] = None


async def get_kafka_consumer() -> KafkaConsumerManager:
    """Get the global Kafka consumer instance."""
    global _consumer_manager
    if _consumer_manager is None:
        _consumer_manager = KafkaConsumerManager()
    return _consumer_manager
