# src/api/conversation.py
from fastapi import APIRouter, HTTPException
from src.services.conversation_service import ConversationService
from src.services.types import Message
from typing import List, Dict
from src.services.types import Conversation

router = APIRouter(tags=["Conversation"])
conversation_service = ConversationService()


@router.get("/conversation/list")
async def list_conversations(user_id: str) -> List[Conversation]:
    """List the conversations"""
    result = await conversation_service._list_conversation(user_id)
    if not result:
        raise HTTPException(status_code=404, detail="User not found")
    return result


@router.post("/conversation/create")
async def create_conversation(app_name: str, user_id: str) -> Conversation:
    """Create a new conversation"""
    result = await conversation_service._create_conversation(app_name, user_id)
    return result


@router.get("/message/list")
async def list_messages(conversation_id: str) -> List[Message]:
    """List the messages for a conversation"""
    result = await conversation_service._list_messages(conversation_id)
    if not result:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return result


@router.delete("/conversation/delete")
async def delete_conversation(conversation_id: str) -> Dict[str, str]:
    """Delete a conversation and all its related data including messages, events, tasks, etc."""
    result = await conversation_service._delete_conversation(conversation_id)
    if not result:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"message": "Conversation deleted successfully"}
