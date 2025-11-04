# src/domain/schemas/conversation.py
from pydantic import BaseModel
import uuid


class ConversationUpdate(BaseModel):
    """What users can update"""

    conversation_id: uuid.UUID
    name: str
    is_active: bool
