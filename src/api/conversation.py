# src/api/conversation.py
from fastapi import APIRouter, HTTPException
from src.services.conversation_service import ConversationService
from src.utils.logger_conf import logger
from src.services.types import Message
from typing import List
from src.services.types import Conversation

router = APIRouter(tags=["Conversation"])
conversation_service = ConversationService()


@router.get("/conversation/list")
async def list_conversations(user_id: str) -> List[Conversation]:
    """List the conversations"""
    try:
        result = await conversation_service._list_conversation(user_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/conversation/create")
async def create_conversation(app_name: str, user_id: str) -> Conversation:
    """Create a new conversation"""
    try:
        result = await conversation_service._create_conversation(app_name, user_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/message/list")
async def list_messages(conversation_id: str) -> List[Message | None]:
    """List the messages for a conversation"""
    try:
        result = await conversation_service._list_messages(conversation_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/conversation/delete")
async def delete_conversation(conversation_id: str) -> str:
    """Delete a conversation and all its related data including messages, events, tasks, etc."""
    try:
        result = await conversation_service._delete_conversation(conversation_id)
        return result
    except Exception as e:
        logger.error(f"Error deleting conversation {conversation_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
