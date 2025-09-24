# src/api/chat.py
from fastapi import APIRouter, HTTPException
from src.models.chat import ChatRequest, ChatResponse
from src.services.chat_service import ChatService
from fastapi.responses import StreamingResponse
from src.middleware.endpoint_manager import endpoint_protection

router = APIRouter(prefix="/chat", tags=["Chat"])
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
    if len(request.message.parts[0].text) == 0 or request.message.parts[0].text is None:
        raise HTTPException(status_code=400, detail="Message is required")

    if len(request.message.parts[0].text) > 30000:
        raise HTTPException(status_code=400, detail="Message is too long")

    try:
        response, sources = await chat_service.ask(request)
        return ChatResponse(message=response, sources=sources)
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
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception as e:
        raise e
