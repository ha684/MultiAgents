# src/api/chat.py
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from src.domain.schemas.chat import ChatRequest, Message
from src.middlewares.endpoint_manager import endpoint_protection
from src.services.chat_service import ChatService
from src.dependencies.auth import get_current_user

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
