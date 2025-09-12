from fastapi import APIRouter, HTTPException
from src.services.conversation_service import ConversationService
from src.utils.logger_conf import logger
from typing import Optional
from ..services.types import (
    CreateConversationResponse,
    GetEventResponse,
    ListAgentResponse,
    ListConversationResponse,
    ListMessageResponse,
    ListTaskResponse,
    PendingMessageResponse,
    RegisterAgentResponse,
)

router = APIRouter(tags=["Conversation"])
server_instance = ConversationService()


@router.get("/conversation/list", response_model=ListConversationResponse)
async def list_conversations(
    app_name: Optional[str], user_id: Optional[str]
) -> ListConversationResponse:
    """List the conversations"""
    try:
        result = await server_instance._list_conversation(app_name, user_id)
        logger.info(f"Listed {len(result.result)} conversations")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/conversation/create", response_model=CreateConversationResponse)
async def create_conversation(
    app_name: str, user_id: str
) -> CreateConversationResponse:
    """Create a new conversation"""
    try:
        result = await server_instance._create_conversation(app_name, user_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agent/list", response_model=ListAgentResponse)
async def list_remote_agents() -> ListAgentResponse:
    """List the remote agents"""
    try:
        result = await server_instance._list_agents()
        logger.info(f"Listed {len(result.result)} remote agents")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agent/register")
async def add_remote_agent(
    path: str,
    app_name: str,
) -> RegisterAgentResponse:
    """Add a remote agent"""
    try:
        if not path.startswith("http"):
            result = await server_instance._register_agent(path, app_name)
        elif path.startswith("http"):
            path = path.replace("http://", "")
            result = await server_instance._register_agent(path, app_name)
        elif path.startswith("https"):
            path = path.replace("https://", "")
            result = await server_instance._register_agent(path, app_name)
        else:
            raise HTTPException(status_code=400, detail="Invalid path")
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/events/all", response_model=GetEventResponse)
async def get_events_all(conversation_id: Optional[str] = None) -> GetEventResponse:
    """Get all events"""
    try:
        result = await server_instance._get_events_all(conversation_id=conversation_id)
        logger.info(f"Got {len(result.result)} events")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/message/pending", response_model=PendingMessageResponse)
async def get_processing_messages() -> PendingMessageResponse:
    """Get the pending messages"""
    try:
        result = await server_instance._pending_messages()
        logger.info(f"Got {len(result.result)} pending messages")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/task/list", response_model=ListTaskResponse)
async def get_tasks() -> ListTaskResponse:
    """List the tasks"""
    try:
        result = await server_instance._list_tasks()
        logger.info(f"Got {len(result.result)} tasks")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/message/list", response_model=ListMessageResponse)
async def list_messages(conversation_id: str) -> ListMessageResponse:
    """List the messages for a conversation"""
    try:
        result = await server_instance._list_messages(conversation_id)
        logger.info(
            f"Got {len(result.result)} messages for conversation {conversation_id}"
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/api_key/update", response_model=dict[str, str])
async def update_api_key(api_key: str, app_name: str) -> dict[str, str]:
    """Update the API key"""
    try:
        result = await server_instance.update_api_key(api_key, app_name)
        logger.info("Updated API key")
        return {"status": "success", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/conversation/delete", response_model=dict[str, str])
async def delete_conversation(conversation_id: str) -> dict[str, str]:
    """Delete a conversation and all its related data including messages, events, tasks, etc."""
    try:
        result = await server_instance._delete_conversation(conversation_id)
        return {"status": "success", "result": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting conversation {conversation_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agent/initialize")
async def initialize_agent(
    app_name: str,
) -> dict[str, str]:
    """Initialize the agent"""
    try:
        result = await server_instance._initialize_host(app_name)
        return {"status": "success", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
