# src/api/conversation.py
from fastapi import APIRouter
from src.services.conversation_service import ConversationService
from src.services.types import Message
from typing import List, Dict
from src.services.types import Conversation
import uuid

router = APIRouter(tags=["Conversation"])
conversation_service = ConversationService()


@router.get("/conversation/list")
async def list_conversations(user_id: str) -> List[Conversation]:
    """List the conversations"""
    result = await conversation_service.list_conversation(user_id)
    return result


@router.post("/conversation/create")
async def create_conversation(app_name: str, user_id: str) -> Conversation:
    """Create a new conversation"""
    result = await conversation_service.create_conversation(app_name, user_id)
    return result


@router.get("/message/list")
async def list_messages(conversation_id: uuid.UUID, user_id: str) -> List[Message]:
    """List the messages for a conversation"""
    result = await conversation_service.list_messages(conversation_id, user_id)
    return result


@router.delete("/conversation/delete")
async def delete_conversation(
    conversation_id: uuid.UUID, user_id: str
) -> Dict[str, str]:
    """Delete a conversation and all its related data including messages, events, tasks, etc."""
    await conversation_service.delete_conversation(conversation_id, user_id)
    return {"message": "Conversation deleted successfully"}


@router.patch("/conversation/update")
async def update_conversation(
    conversation_id: uuid.UUID, user_id: str, active: bool, name: str
) -> Conversation:
    """Update a conversation"""
    result = await conversation_service.update_conversation(
        conversation_id, user_id, active, name
    )
    return result
