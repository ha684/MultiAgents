# src/api/chat.py
from fastapi import APIRouter, HTTPException, Request, Body
from src.models.chat import ChatRequest, ChatResponse
from src.services.chat_service import ChatService
from src.utils.logger_conf import logger
from fastapi.responses import StreamingResponse
from ..common.types import Message
from src.services.conversation_service import ConversationService
from src.services.types import SendMessageResponse
from src.middleware.endpoint_manager import endpoint_protection


router = APIRouter(prefix="/chat", tags=["Chat"])
server_instance = ConversationService()
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
) -> ChatResponse:
    try:
        response, sources = await chat_service.ask(request)
        result = ChatResponse(message=response, sources=sources)
        return result
    except Exception as e:
        logger.exception(e)
        raise HTTPException(status_code=500, detail=f"Error creating message: {str(e)}")


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
    try:
        return StreamingResponse(
            await chat_service.ask_sse(request),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception as e:
        logger.exception(e)
        raise HTTPException(status_code=500, detail=f"Error creating message: {str(e)}")


@router.post("/message/send")
async def send_message(
    request: Request,
    message: Message = Body(
        examples={
            "role": "user",
            "parts": [{"type": "text", "text": "string"}],
            "metadata": {
                "conversation_id": "id",
                "conversation_name": "",
                "context_id": "test",
                "user_id": "test",
                "app_name": "test",
                "kb_id": "456",
            },
        }
    ),
) -> SendMessageResponse:
    """Send a message to the conversation"""
    try:
        conversation_id = (
            message.metadata.get("conversation_id") if message.metadata else None
        )
        logger.info(f"Sent message to conversation {conversation_id}")
        result = await server_instance._send_message(message)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/message/send/sse")
async def send_message_sse(
    request: Request,
    message: Message = Body(
        examples={
            "role": "user",
            "parts": [{"type": "text", "text": "Hello, how are you?"}],
            "metadata": {
                "conversation_id": "123",
                "conversation_name": "test",
                "context_id": "test",
                "user_id": "test",
                "app_name": "test",
                "kb_id": "456",
            },
        }
    ),
) -> StreamingResponse:
    """Send a message to the conversation with SSE streaming"""
    try:
        return StreamingResponse(
            server_instance._send_message_stream(message),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
