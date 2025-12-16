# src/api/chat.py
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from src.dependencies.auth import get_current_user
from src.domain.schemas.chat import ChatRequest, Message
from src.domain.schemas.chat_task import (
    ChatTaskRequest,
    ChatTaskResponse,
    ChatTaskStatus,
    ChatTaskStatusResponse,
)
from src.middlewares.endpoint_manager import endpoint_protection
from src.services.chat_service import ChatService
from src.services.chat_stream_service import chat_stream_service
from src.utils.logger_conf import logger

router = APIRouter(
    prefix="/chat", tags=["Chat"], dependencies=[Depends(get_current_user)]
)
chat_service = ChatService()


@router.post("/ask")
@endpoint_protection(
    endpoint_name="/ask",
    max_concurrent=80,
    max_queue_size=300,
    queue_timeout=300,
    processing_timeout=600,
)
async def ask(
    request: ChatRequest,
) -> Message:
    if len(request.message.parts[0].text) == 0 or request.message.parts[0].text is None:
        raise HTTPException(status_code=400, detail="Message is required")

    if len(request.message.parts[0].text) > 30000:
        raise HTTPException(status_code=400, detail="Message is too long")

    try:
        response = await chat_service.ask(request)
        return response
    except Exception as e:
        raise e


@router.post("/ask/sse")
@endpoint_protection(
    endpoint_name="/ask/sse",
    max_concurrent=80,
    max_queue_size=300,
    queue_timeout=300,
    processing_timeout=600,
)
async def ask_sse(
    request: ChatRequest,
) -> StreamingResponse:
    if len(request.message.parts[0].text) == 0 or request.message.parts[0].text is None:
        raise HTTPException(status_code=400, detail="Message is required")

    if len(request.message.parts[0].text) > 30000:
        raise HTTPException(status_code=400, detail="Message is too long")

    try:
        return StreamingResponse(
            await chat_service.ask_sse(request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception as e:
        raise e


@router.post("/ask/task", response_model=ChatTaskResponse)
@endpoint_protection(
    endpoint_name="/ask/task",
    max_concurrent=100,
    max_queue_size=500,
    queue_timeout=30,
    processing_timeout=60,
)
async def create_chat_task(
    request: ChatTaskRequest,
) -> ChatTaskResponse:
    """
    Create a chat task for processing.

    This endpoint creates a task that will be processed by a Celery worker.
    The response includes a task_id and websocket_url for streaming.

    ## Flow:
    1. POST /chat/ask/task - Create task, get task_id
    2. Connect to WebSocket /chat/stream/{task_id}
    3. Receive streaming events via WebSocket
    4. (Optional) Send commands: {"action": "stop"} to cancel

    ## Benefits over SSE:
    - Reconnection support: If disconnected, connect again with last_event_id
    - Late subscriber support: Connect after task started, replay from beginning
    - Cancellation: Send stop command to cancel generation
    - Thinking preservation: Thinking content is saved and retrievable

    ## Example:
    ```python
    # Create task
    response = requests.post("/chat/ask/task", json={
        "conversation_id": "...",
        "user_id": "...",
        "kb_id": "...",
        "message_text": "What is...",
        "agentic": True
    })
    task_id = response.json()["task_id"]

    # Connect to WebSocket
    ws = websocket.connect(f"/chat/stream/{task_id}")
    for message in ws:
        print(message)
    ```
    """
    if not request.message_text or len(request.message_text) == 0:
        raise HTTPException(status_code=400, detail="Message is required")

    if len(request.message_text) > 30000:
        raise HTTPException(status_code=400, detail="Message is too long")

    try:
        task_id = await chat_stream_service.create_chat_task(
            conversation_id=request.conversation_id,
            user_id=request.user_id,
            kb_id=request.kb_id,
            message_text=request.message_text,
            message_metadata=request.message_metadata,
            agentic=request.agentic,
            web_search=request.web_search,
        )

        if not task_id:
            raise HTTPException(
                status_code=500,
                detail="Failed to create chat task",
            )

        return ChatTaskResponse(
            task_id=task_id,
            status=ChatTaskStatus.PENDING,
            websocket_url=f"/chat/stream/{task_id}",
            message="Task created successfully. Connect to WebSocket to receive streaming updates.",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error creating chat task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/task/{task_id}/status", response_model=ChatTaskStatusResponse)
async def get_task_status(task_id: str) -> ChatTaskStatusResponse:
    """
    Get the status of a chat task.

    ## Status Values:
    - `pending`: Task is queued but not started
    - `streaming`: Task is actively generating response
    - `complete`: Task finished successfully
    - `cancelled`: Task was cancelled by user
    - `error`: Task failed with an error
    """
    try:
        status_info = await chat_stream_service.get_task_status(task_id)

        if not status_info:
            raise HTTPException(status_code=404, detail="Task not found")

        return ChatTaskStatusResponse(
            task_id=task_id,
            status=ChatTaskStatus(status_info["status"]),
            created_at=status_info.get("metadata", {}).get("created_at"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting task status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/task/{task_id}/cancel")
async def cancel_task(task_id: str) -> dict[str, Any]:
    """
    Request cancellation of a chat task.

    The task will be cancelled as soon as possible.
    Note: Some tokens may still be generated before cancellation takes effect.
    """
    try:
        success = await chat_stream_service.cancel_task(task_id)

        if success:
            return {
                "task_id": task_id,
                "status": "cancellation_requested",
                "message": "Task cancellation has been requested",
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to request task cancellation",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error cancelling task: {e}")
        raise HTTPException(status_code=500, detail=str(e))
