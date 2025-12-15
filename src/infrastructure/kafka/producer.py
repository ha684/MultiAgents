# src/infrastructure/kafka/producer.py
"""Kafka producer for LLM streaming events."""

import asyncio
import json
from typing import Any, Optional

from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError

from src.core.config.settings import settings
from src.infrastructure.kafka.schemas import (
    BaseKafkaMessage,
    DeltaMessage,
    DoneMessage,
    ErrorMessage,
    MetaMessage,
)
from src.utils.logger_conf import logger


class KafkaProducerManager:
    """Manages Kafka producer for LLM streaming events."""

    _instance: Optional["KafkaProducerManager"] = None
    _producer: Optional[AIOKafkaProducer] = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __new__(cls) -> "KafkaProducerManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self._topic = settings.kafka_topic_llm_responses
        self._bootstrap_servers = settings.kafka_bootstrap_servers
        self._security_protocol = settings.kafka_security_protocol

    async def start(self) -> None:
        """Start the Kafka producer."""
        async with self._lock:
            if self._producer is not None:
                return

            try:
                self._producer = AIOKafkaProducer(
                    bootstrap_servers=self._bootstrap_servers,
                    security_protocol=self._security_protocol,
                    value_serializer=lambda v: json.dumps(v, default=str).encode(
                        "utf-8"
                    ),
                    key_serializer=lambda k: k.encode("utf-8") if k else None,
                    acks="all",
                    enable_idempotence=True,
                    max_in_flight_requests_per_connection=1,
                )
                await self._producer.start()
                logger.info(
                    f"Kafka producer started, connected to {self._bootstrap_servers}"
                )
            except Exception as e:
                logger.error(f"Failed to start Kafka producer: {e}")
                raise

    async def stop(self) -> None:
        """Stop the Kafka producer."""
        async with self._lock:
            if self._producer is not None:
                await self._producer.stop()
                self._producer = None
                logger.info("Kafka producer stopped")

    async def _ensure_started(self) -> None:
        """Ensure the producer is started."""
        if self._producer is None:
            await self.start()

    async def send_message(
        self,
        request_id: str,
        message: BaseKafkaMessage,
    ) -> tuple[int, int]:
        """
        Send a message to Kafka.

        Args:
            request_id: The request ID (used as partition key)
            message: The message to send

        Returns:
            Tuple of (partition, offset)
        """
        await self._ensure_started()

        try:
            # Use request_id as key to ensure all messages for a request
            # go to the same partition (maintaining order)
            result = await self._producer.send_and_wait(
                topic=self._topic,
                key=request_id,
                value=message.model_dump(mode="json"),
                headers=[
                    ("request_id", request_id.encode("utf-8")),
                    ("type", message.type.encode("utf-8")),
                ],
            )

            logger.debug(
                f"Sent Kafka message: request_id={request_id}, "
                f"type={message.type}, partition={result.partition}, offset={result.offset}"
            )

            return result.partition, result.offset

        except KafkaError as e:
            logger.error(f"Failed to send Kafka message: {e}")
            raise

    async def send_delta(
        self,
        request_id: str,
        delta: str,
        seq: int = 0,
    ) -> tuple[int, int]:
        """Send a delta (partial token) message."""
        message = DeltaMessage(
            request_id=request_id,
            delta=delta,
            seq=seq,
        )
        return await self.send_message(request_id, message)

    async def send_meta(
        self,
        request_id: str,
        model: Optional[str] = None,
        prompt_tokens: Optional[int] = None,
        conversation_id: Optional[str] = None,
        kb_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> tuple[int, int]:
        """Send a metadata message."""
        message = MetaMessage(
            request_id=request_id,
            model=model,
            prompt_tokens=prompt_tokens,
            conversation_id=conversation_id,
            kb_id=kb_id,
            user_id=user_id,
            metadata=metadata or {},
        )
        return await self.send_message(request_id, message)

    async def send_done(
        self,
        request_id: str,
        total_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        prompt_tokens: Optional[int] = None,
        finish_reason: str = "stop",
        final_content: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        seq: int = 0,
    ) -> tuple[int, int]:
        """Send a done (completion) message."""
        message = DoneMessage(
            request_id=request_id,
            total_tokens=total_tokens,
            completion_tokens=completion_tokens,
            prompt_tokens=prompt_tokens,
            finish_reason=finish_reason,
            final_content=final_content,
            metadata=metadata or {},
            seq=seq,
        )
        return await self.send_message(request_id, message)

    async def send_error(
        self,
        request_id: str,
        message: str,
        error_code: str = "generation_error",
        details: Optional[dict[str, Any]] = None,
        seq: int = 0,
    ) -> tuple[int, int]:
        """Send an error message."""
        error_msg = ErrorMessage(
            request_id=request_id,
            error_code=error_code,
            message=message,
            details=details,
            seq=seq,
        )
        return await self.send_message(request_id, error_msg)


# Global producer instance
_producer_manager: Optional[KafkaProducerManager] = None


async def get_kafka_producer() -> KafkaProducerManager:
    """Get the global Kafka producer instance."""
    global _producer_manager
    if _producer_manager is None:
        _producer_manager = KafkaProducerManager()
        await _producer_manager.start()
    return _producer_manager
