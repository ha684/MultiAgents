# src/api/streaming_chat.py
"""
Kafka-backed LLM streaming endpoints with resume capability.

This module provides:
- POST /v1/chat/completions - Start a generation request
- GET /v1/chat/stream/{request_id} - SSE streaming with resume
- WebSocket /v1/chat/ws - WebSocket streaming with resume
- GET /v1/chat/status/{request_id} - Get stream status
"""

import asyncio
import json
import uuid
from typing import Any, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from uuid_extensions import uuid7

from src.core.config.celery_app import celery_app
from src.dependencies.auth import get_current_user
from src.infrastructure.kafka.consumer import (
    get_kafka_consumer,
    stream_index_store,
)
from src.infrastructure.kafka.schemas import (
    DoneMessage,
    ErrorMessage,
    StreamIndex,
    StreamStatus,
    StreamStatusResponse,
)
from src.utils.logger_conf import logger

router = APIRouter(prefix="/v1/chat", tags=["Streaming Chat"])


# Request/Response schemas
class ChatCompletionRequest(BaseModel):
    """Request to start a chat completion."""

    conversation_id: Optional[str] = None
    kb_id: Optional[str] = None
    user_id: Optional[str] = None
    messages: list[dict[str, Any]] = Field(..., min_length=1)
    model: Optional[str] = None
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: Optional[int] = Field(default=None, ge=1, le=32000)
    agentic: bool = False
    web_search: bool = False
    use_rag: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatCompletionResponse(BaseModel):
    """Response after starting a chat completion."""

    request_id: str
    status: str = "queued"
    message: str = "Generation request queued successfully"


class WebSocketMessage(BaseModel):
    """WebSocket message from client."""

    request_id: str
    cursor: Optional[str] = None


# Endpoints
@router.post("/completions")
async def start_chat_completion(
    request: ChatCompletionRequest,
    current_user: dict = Depends(get_current_user),
) -> ChatCompletionResponse:
    """
    Start a new chat completion request.

    This endpoint queues a background task that will stream tokens to Kafka.
    Use the returned request_id to connect to SSE or WebSocket for the stream.

    Returns immediately with the request_id and queued status.
    """
    # Generate request_id (use message ID pattern)
    request_id = uuid7().hex

    # Validate messages
    if not request.messages:
        raise HTTPException(status_code=400, detail="Messages list cannot be empty")

    last_message = request.messages[-1]
    if not last_message.get("content"):
        raise HTTPException(status_code=400, detail="Last message must have content")

    # Validate UUID fields
    if request.conversation_id:
        try:
            uuid.UUID(request.conversation_id)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid conversation_id format"
            )

    if request.kb_id:
        try:
            uuid.UUID(request.kb_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid kb_id format")

    # Get user_id from token if not provided
    user_id = request.user_id or current_user.get("user_id", current_user.get("sub"))

    try:
        # Queue Celery task
        task = celery_app.send_task(
            "tasks.generate_and_stream",
            args=[],
            kwargs={
                "request_id": request_id,
                "messages": request.messages,
                "model": request.model,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "conversation_id": request.conversation_id,
                "kb_id": request.kb_id,
                "user_id": user_id,
                "agentic": request.agentic,
                "web_search": request.web_search,
                "use_rag": request.use_rag,
                "metadata": request.metadata,
            },
            queue="llm_streaming",
        )

        logger.info(
            f"Queued generation task: request_id={request_id}, task_id={task.id}"
        )

        return ChatCompletionResponse(
            request_id=request_id,
            status="queued",
            message="Generation request queued successfully",
        )

    except Exception as e:
        logger.error(f"Failed to queue generation task: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to queue generation request",
        )


@router.get("/stream/{request_id}")
async def stream_sse(
    request_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
) -> StreamingResponse:
    """
    SSE endpoint for streaming chat completions with resume support.

    Supports resume via Last-Event-ID header:
    - If Last-Event-ID is provided, continues from that cursor
    - If not provided, starts from the beginning of the stream

    SSE Event format:
    - id: cursor (partition:offset)
    - event: delta/meta/done/error
    - data: JSON payload
    """
    # Validate request_id format
    if len(request_id) != 32:
        raise HTTPException(status_code=400, detail="Invalid request_id format")

    # Get Last-Event-ID for resume
    last_event_id = request.headers.get("Last-Event-ID")
    cursor = None

    if last_event_id:
        try:
            cursor = StreamIndex.from_cursor(last_event_id)
            logger.info(
                f"Resuming stream for request_id={request_id} from cursor={last_event_id}"
            )
        except ValueError:
            logger.warning(f"Invalid Last-Event-ID format: {last_event_id}")

    async def event_generator():
        """Generate SSE events from Kafka."""
        consumer = await get_kafka_consumer()
        queue = None

        try:
            # Check if we need to replay (resume from cursor)
            if cursor:
                # Replay from cursor
                async for message, msg_cursor in consumer.replay_from_cursor(
                    request_id=request_id,
                    cursor=cursor,
                ):
                    # Check if client disconnected
                    if await request.is_disconnected():
                        break

                    yield format_sse_event(message, msg_cursor)

                    # Stop on terminal message
                    if isinstance(message, (DoneMessage, ErrorMessage)):
                        return

            else:
                # Check if stream already exists
                index_info = await stream_index_store.get(request_id)

                if index_info:
                    # Replay from beginning
                    async for message, msg_cursor in consumer.replay_from_cursor(
                        request_id=request_id,
                        cursor=None,  # From beginning
                    ):
                        if await request.is_disconnected():
                            break

                        yield format_sse_event(message, msg_cursor)

                        if isinstance(message, (DoneMessage, ErrorMessage)):
                            return

                else:
                    # Subscribe to live updates
                    queue = await consumer.subscribe(request_id)

                    # Wait for messages with timeout
                    timeout = 300  # 5 minutes
                    start_time = asyncio.get_event_loop().time()

                    while True:
                        if await request.is_disconnected():
                            break

                        elapsed = asyncio.get_event_loop().time() - start_time
                        if elapsed > timeout:
                            yield format_sse_event(
                                ErrorMessage(
                                    request_id=request_id,
                                    error_code="timeout",
                                    message="Stream timeout",
                                ),
                                StreamIndex(partition=0, offset=0),
                            )
                            break

                        try:
                            message, msg_cursor = await asyncio.wait_for(
                                queue.get(),
                                timeout=1.0,
                            )

                            yield format_sse_event(message, msg_cursor)

                            if isinstance(message, (DoneMessage, ErrorMessage)):
                                break

                        except asyncio.TimeoutError:
                            # Send keepalive comment
                            yield ": keepalive\n\n"
                            continue

        except Exception as e:
            logger.error(f"Error in SSE stream for request_id={request_id}: {e}")
            yield format_sse_event(
                ErrorMessage(
                    request_id=request_id,
                    error_code="stream_error",
                    message=str(e),
                ),
                StreamIndex(partition=0, offset=0),
            )

        finally:
            if queue:
                await consumer.unsubscribe(request_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.websocket("/ws")
async def websocket_stream(
    websocket: WebSocket,
    # Note: WebSocket auth needs to be handled differently
):
    """
    WebSocket endpoint for streaming chat completions with resume support.

    Protocol:
    1. Client connects
    2. Client sends: {"request_id": "...", "cursor": "partition:offset" | null}
    3. Server streams JSON messages: {"type": "...", "data": {...}, "cursor": "..."}
    4. On terminal message (done/error), server closes connection

    To resume, reconnect and provide the last cursor received.
    """
    await websocket.accept()
    logger.info("WebSocket connection accepted")

    request_id = None
    queue = None
    consumer = None

    try:
        # Wait for initial message with request_id
        try:
            init_data = await asyncio.wait_for(
                websocket.receive_json(),
                timeout=10.0,
            )
        except asyncio.TimeoutError:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": "Timeout waiting for initial message",
                }
            )
            await websocket.close()
            return

        try:
            ws_message = WebSocketMessage(**init_data)
            request_id = ws_message.request_id
        except Exception as e:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": f"Invalid message format: {e}",
                }
            )
            await websocket.close()
            return

        # Validate request_id
        if len(request_id) != 32:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": "Invalid request_id format",
                }
            )
            await websocket.close()
            return

        # Parse cursor if provided
        cursor = None
        if ws_message.cursor:
            try:
                cursor = StreamIndex.from_cursor(ws_message.cursor)
                logger.info(
                    f"WebSocket resuming request_id={request_id} from cursor={ws_message.cursor}"
                )
            except ValueError:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Invalid cursor format",
                    }
                )
                await websocket.close()
                return

        consumer = await get_kafka_consumer()

        # Send acknowledgment
        await websocket.send_json(
            {
                "type": "connected",
                "request_id": request_id,
                "message": "Connected to stream",
            }
        )

        # Handle streaming
        if cursor:
            # Replay from cursor
            async for message, msg_cursor in consumer.replay_from_cursor(
                request_id=request_id,
                cursor=cursor,
            ):
                await websocket.send_json(format_ws_message(message, msg_cursor))

                if isinstance(message, (DoneMessage, ErrorMessage)):
                    await websocket.close()
                    return
        else:
            # Check if stream exists
            index_info = await stream_index_store.get(request_id)

            if index_info:
                # Replay from beginning
                async for message, msg_cursor in consumer.replay_from_cursor(
                    request_id=request_id,
                    cursor=None,
                ):
                    await websocket.send_json(format_ws_message(message, msg_cursor))

                    if isinstance(message, (DoneMessage, ErrorMessage)):
                        await websocket.close()
                        return
            else:
                # Subscribe to live updates
                queue = await consumer.subscribe(request_id)

                timeout = 300
                start_time = asyncio.get_event_loop().time()

                while True:
                    elapsed = asyncio.get_event_loop().time() - start_time
                    if elapsed > timeout:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": "Stream timeout",
                            }
                        )
                        break

                    try:
                        message, msg_cursor = await asyncio.wait_for(
                            queue.get(),
                            timeout=30.0,
                        )

                        await websocket.send_json(
                            format_ws_message(message, msg_cursor)
                        )

                        if isinstance(message, (DoneMessage, ErrorMessage)):
                            break

                    except asyncio.TimeoutError:
                        # Send ping
                        await websocket.send_json({"type": "ping"})
                        continue

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for request_id={request_id}")
    except Exception as e:
        logger.error(f"WebSocket error for request_id={request_id}: {e}")
        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": str(e),
                }
            )
        except:
            pass
    finally:
        if queue and consumer and request_id:
            await consumer.unsubscribe(request_id, queue)
        try:
            await websocket.close()
        except:
            pass


@router.get("/status/{request_id}")
async def get_stream_status(
    request_id: str,
    current_user: dict = Depends(get_current_user),
) -> StreamStatusResponse:
    """
    Get the status of a streaming request.

    Returns:
    - status: queued/running/done/error
    - cursor: Latest cursor if available
    - timestamps and metadata
    """
    # Validate request_id format
    if len(request_id) != 32:
        raise HTTPException(status_code=400, detail="Invalid request_id format")

    # Check stream index store
    index_info = await stream_index_store.get(request_id)

    if index_info:
        cursor = StreamIndex(
            partition=index_info.partition,
            offset=index_info.last_offset,
        ).to_cursor()

        status = (
            StreamStatus(index_info.status)
            if index_info.status in ["running", "done", "error"]
            else StreamStatus.RUNNING
        )

        return StreamStatusResponse(
            request_id=request_id,
            status=status,
            cursor=cursor,
            created_at=index_info.created_at,
            metadata={
                "partition": index_info.partition,
                "start_offset": index_info.start_offset,
                "last_offset": index_info.last_offset,
            },
        )

    # Check Celery task status
    try:
        task_result = celery_app.AsyncResult(request_id)

        if task_result.state == "PENDING":
            return StreamStatusResponse(
                request_id=request_id,
                status=StreamStatus.QUEUED,
            )
        elif task_result.state == "STARTED" or task_result.state == "PROGRESS":
            return StreamStatusResponse(
                request_id=request_id,
                status=StreamStatus.RUNNING,
            )
        elif task_result.state == "SUCCESS":
            return StreamStatusResponse(
                request_id=request_id,
                status=StreamStatus.DONE,
            )
        elif task_result.state == "FAILURE":
            return StreamStatusResponse(
                request_id=request_id,
                status=StreamStatus.ERROR,
                error=str(task_result.info) if task_result.info else "Unknown error",
            )
    except Exception as e:
        logger.warning(f"Could not get Celery task status: {e}")

    # Not found
    raise HTTPException(
        status_code=404,
        detail=f"Stream not found: {request_id}",
    )


# Helper functions
def format_sse_event(message: Any, cursor: StreamIndex) -> str:
    """Format a Kafka message as an SSE event."""
    cursor_str = cursor.to_cursor()

    data = (
        message.model_dump(mode="json") if hasattr(message, "model_dump") else message
    )

    event_type = data.get("type", "message")

    return f"id: {cursor_str}\nevent: {event_type}\ndata: {json.dumps(data)}\n\n"


def format_ws_message(message: Any, cursor: StreamIndex) -> dict[str, Any]:
    """Format a Kafka message for WebSocket."""
    data = (
        message.model_dump(mode="json") if hasattr(message, "model_dump") else message
    )

    return {
        "type": data.get("type", "message"),
        "data": data,
        "cursor": cursor.to_cursor(),
    }
