# src/infrastructure/kafka/schemas.py
"""Kafka message schemas for LLM streaming."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from uuid_extensions import uuid7


class KafkaMessageType(str, Enum):
    """Types of Kafka messages for LLM streaming."""

    DELTA = "delta"  # Partial token/text
    META = "meta"  # Metadata (model name, prompt tokens, etc.)
    DONE = "done"  # Completion signal with final usage
    ERROR = "error"  # Error information (terminal)


class StreamIndex(BaseModel):
    """Represents a Kafka stream index/cursor for resume capability."""

    partition: int
    offset: int

    def to_cursor(self) -> str:
        """Convert to cursor string format 'partition:offset'"""
        return f"{self.partition}:{self.offset}"

    @classmethod
    def from_cursor(cls, cursor: str) -> "StreamIndex":
        """Parse cursor string format 'partition:offset'"""
        parts = cursor.split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid cursor format: {cursor}")
        return cls(partition=int(parts[0]), offset=int(parts[1]))


class BaseKafkaMessage(BaseModel):
    """Base class for all Kafka messages."""

    request_id: str = Field(
        ..., description="Unique identifier for the generation request"
    )
    type: KafkaMessageType
    created_at: datetime = Field(default_factory=lambda: datetime.now(ZoneInfo("UTC")))
    seq: int = Field(
        default=0, description="Sequence number for ordering within request"
    )

    class Config:
        use_enum_values = True


class DeltaMessage(BaseKafkaMessage):
    """Message containing a partial token/text delta."""

    type: KafkaMessageType = KafkaMessageType.DELTA
    delta: str = Field(..., description="Partial token text")


class MetaMessage(BaseKafkaMessage):
    """Message containing metadata about the generation."""

    type: KafkaMessageType = KafkaMessageType.META
    model: Optional[str] = None
    prompt_tokens: Optional[int] = None
    conversation_id: Optional[str] = None
    kb_id: Optional[str] = None
    user_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DoneMessage(BaseKafkaMessage):
    """Message signaling completion of generation."""

    type: KafkaMessageType = KafkaMessageType.DONE
    total_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    prompt_tokens: Optional[int] = None
    finish_reason: str = "stop"
    final_content: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ErrorMessage(BaseKafkaMessage):
    """Message signaling an error (terminal)."""

    type: KafkaMessageType = KafkaMessageType.ERROR
    error_code: str = "generation_error"
    message: str = Field(..., description="Error message")
    details: Optional[dict[str, Any]] = None


# Union type for all message types
KafkaMessage = DeltaMessage | MetaMessage | DoneMessage | ErrorMessage


class StreamRequest(BaseModel):
    """Request to start a streaming generation."""

    request_id: str = Field(default_factory=lambda: uuid7().hex)
    conversation_id: Optional[str] = None
    kb_id: Optional[str] = None
    user_id: Optional[str] = None
    messages: list[dict[str, Any]] = Field(default_factory=list)
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    agentic: bool = False
    web_search: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class StreamStatus(str, Enum):
    """Status of a streaming request."""

    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


class StreamStatusResponse(BaseModel):
    """Response for stream status endpoint."""

    request_id: str
    status: StreamStatus
    cursor: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
