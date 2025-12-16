# src/domain/schemas/chat_task.py
"""
Domain schemas for chat task management.

These schemas define the data structures for:
- Chat task creation and tracking
- WebSocket communication
- Task status and results
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ChatTaskStatus(str, Enum):
    """Status of a chat inference task"""

    PENDING = "pending"
    STREAMING = "streaming"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    ERROR = "error"


class ChatTaskRequest(BaseModel):
    """Request to create a new chat task"""

    conversation_id: uuid.UUID
    user_id: str
    kb_id: uuid.UUID
    message_text: str
    message_metadata: dict[str, Any] = Field(default_factory=dict)
    agentic: bool = False
    web_search: bool = False


class ChatTaskResponse(BaseModel):
    """Response when a chat task is created"""

    task_id: str
    status: ChatTaskStatus
    websocket_url: str
    message: str = "Task queued successfully"

    class Config:
        use_enum_values = True


class ChatTaskStatusResponse(BaseModel):
    """Response for task status queries"""

    task_id: str
    status: ChatTaskStatus
    created_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None

    class Config:
        use_enum_values = True


class WSCommandType(str, Enum):
    """Types of commands client can send via WebSocket"""

    STOP = "stop"
    PING = "ping"
    RESUME = "resume"


class WSCommand(BaseModel):
    """Command sent from client via WebSocket"""

    action: WSCommandType
    last_event_id: str | None = None

    class Config:
        use_enum_values = True


class WSEventType(str, Enum):
    """Types of events sent to client via WebSocket"""

    CONNECTED = "connected"
    MESSAGE_START = "message_start"
    CONTENT_DELTA = "content_block_delta"
    STATUS = "status"
    MESSAGE_STOP = "message_stop"
    ERROR = "error"
    CANCELLED = "cancelled"
    PING = "pong"


class WSEvent(BaseModel):
    """Event sent to client via WebSocket"""

    type: WSEventType
    event_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)

    class Config:
        use_enum_values = True

    def to_json(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict"""
        return {
            "type": self.type,
            "event_id": self.event_id,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }
