# src/domain/schemas/conversation.py
import uuid

from pydantic import BaseModel, field_validator


class ConversationUpdate(BaseModel):
    """What users can update"""

    conversation_id: uuid.UUID
    name: str
    is_active: bool

    @field_validator("name")
    @classmethod
    def truncate_name(cls, v: str) -> str:
        """Truncate to first ~50 words or 255 chars"""
        words = v.split()
        if len(words) > 50:
            return " ".join(words[:50]) + "..."
        if len(v) > 255:
            return v[:252] + "..."
        return v
