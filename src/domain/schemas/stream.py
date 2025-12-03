# src/domain/schemas/stream.py
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo


class StreamEventType(Enum):
    """Standardized stream event types"""

    MESSAGE_START = "message_start"
    MESSAGE_DELTA = "content_block_delta"
    MESSAGE_STOP = "message_stop"
    ERROR = "error"
    STATUS = "status"


@dataclass
class StreamEvent:
    """Standardized stream event structure"""

    type: str
    data: dict[str, Any] = field(default_factory=dict)
    id: str | None = None
    timestamp: str | None = None

    def __post_init__(self):
        if self.id is None:
            self.id = str(uuid.uuid4())
        if self.timestamp is None:
            self.timestamp = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat()


class StreamPhase(Enum):
    """Process phases for status tracking"""

    ANALYSIS = "analysis"
    RETRIEVAL = "retrieval"
    PROCESSING = "processing"
    SYNTHESIS = "synthesis"
    COMPLETE = "complete"
