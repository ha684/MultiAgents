# src/api/conversation.py
from fastapi import APIRouter, HTTPException
from src.services.conversation_service import ConversationService
from src.utils.logger_conf import logger
from typing import Optional
from src.services.types import (
    CreateConversationResponse,
    ListConversationResponse,
    ListMessageResponse,
)

router = APIRouter(tags=["Conversation"])
conversation_service = ConversationService()


@router.get("/conversation/list", response_model=ListConversationResponse)
async def list_conversations(
    app_name: Optional[str], user_id: Optional[str]
) -> ListConversationResponse:
    """List the conversations"""
    try:
        result = await conversation_service._list_conversation(app_name, user_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/conversation/create", response_model=CreateConversationResponse)
async def create_conversation(
    app_name: str, user_id: str
) -> CreateConversationResponse:
    """Create a new conversation"""
    try:
        result = await conversation_service._create_conversation(app_name, user_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/message/list", response_model=ListMessageResponse)
async def list_messages(conversation_id: str) -> ListMessageResponse:
    """List the messages for a conversation"""
    try:
        result = await conversation_service._list_messages(conversation_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/conversation/delete", response_model=dict[str, str])
async def delete_conversation(conversation_id: str) -> dict[str, str]:
    """Delete a conversation and all its related data including messages, events, tasks, etc."""
    try:
        result = await conversation_service._delete_conversation(conversation_id)
        return result
    except Exception as e:
        logger.error(f"Error deleting conversation {conversation_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
