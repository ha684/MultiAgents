# src/api/conversation.py
from typing import Dict, List
import uuid

from fastapi import APIRouter, Depends

from src.agents.shared.manager import execution_manager
from src.core.exceptions.chat_exceptions import ResearchNotFoundError
from src.domain.schemas.chat import Conversation, Message
from src.services.conversation_service import ConversationService
from src.database.models.user import User
from src.dependencies.auth import get_current_user

router = APIRouter(tags=["Conversation"], dependencies=[Depends(get_current_user)])
conversation_service = ConversationService()


@router.get("/conversation/list")
async def list_conversations(
    current_user: User = Depends(get_current_user),
) -> List[Conversation]:
    """List the conversations"""
    result = await conversation_service.list_conversation(current_user.id)
    return result


@router.post("/conversation/create")
async def create_conversation(
    app_name: str, current_user: User = Depends(get_current_user)
) -> Conversation:
    """Create a new conversation"""
    result = await conversation_service.create_conversation(app_name, current_user.id)
    return result


@router.get("/message/list")
async def list_messages(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> List[Message]:
    """List the messages for a conversation"""
    result = await conversation_service.list_messages(conversation_id=conversation_id)
    return result


@router.delete("/conversation/delete")
async def delete_conversation(
    conversation_id: uuid.UUID, current_user: User = Depends(get_current_user)
) -> Dict[str, str]:
    """Delete a conversation and all its related data including messages, events, tasks, etc."""
    await conversation_service.delete_conversation(conversation_id, current_user.id)
    return {"message": "Conversation deleted successfully"}


@router.patch("/conversation/update")
async def update_conversation(
    conversation_id: uuid.UUID,
    active: bool,
    name: str,
    current_user: User = Depends(get_current_user),
) -> Conversation:
    """Update a conversation"""
    result = await conversation_service.update_conversation(
        conversation_id, current_user.id, active, name
    )
    return result


@router.get("/{conversation_id}/status")
async def get_research_status(conversation_id: str):
    """
    Check if research is running (to show "Skip" button in UI)
    """
    execution = execution_manager.get_execution(conversation_id)

    if not execution:
        return {"is_running": False, "conversation_id": conversation_id}

    return {
        "is_running": True,
        "conversation_id": conversation_id,
        "current_node": execution.current_node,
        "started_at": execution.started_at.isoformat(),
        "can_skip": execution.current_node == "research_subgraph_node",
    }


@router.post("/{conversation_id}/skip")
async def skip_research(conversation_id: str):
    """
    User clicks "Skip Research" button in UI
    """
    success = execution_manager.skip_research(conversation_id)

    if not success:
        raise ResearchNotFoundError(conversation_id=conversation_id)

    return {
        "status": "skipped",
        "conversation_id": conversation_id,
    }
