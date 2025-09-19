from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import uuid
from datetime import datetime
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
    data: Dict[str, Any] = field(default_factory=dict)
    id: Optional[str] = None
    timestamp: Optional[str] = None

    def __post_init__(self):
        if self.id is None:
            self.id = str(uuid.uuid4())
        if self.timestamp is None:
            self.timestamp = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat()


class StreamPhase(Enum):
    """Process phases for status tracking"""

    CONTEXT_ANALYSIS = "context_analysis"
    DOCUMENT_RETRIEVAL = "document_retrieval"
    WEB_SEARCH = "web_search"
    CITATION_EXTRACTION = "citation_extraction"
    RESPONSE_GENERATION = "response_generation"
    COMPLETE = "complete"
