# src/tasks/streaming.py
"""Celery task for LLM streaming with Kafka producer."""

import asyncio
import json
import time
from typing import Any, Optional

import httpx
from celery import Task, shared_task
from celery.exceptions import SoftTimeLimitExceeded

from src.core.config.settings import settings
from src.infrastructure.kafka.producer import KafkaProducerManager
from src.infrastructure.kafka.schemas import StreamStatus
from src.utils.logger_conf import logger

# Event loop for async operations in Celery worker
_loop: Optional[asyncio.AbstractEventLoop] = None


def get_or_create_eventloop() -> asyncio.AbstractEventLoop:
    """Get or create event loop for current worker process."""
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop


async def _stream_from_vllm(
    request_id: str,
    messages: list[dict[str, Any]],
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Stream tokens from vLLM and produce to Kafka.

    This function:
    1. Connects to vLLM streaming API
    2. For each token, produces a Kafka message
    3. On completion, produces a done message
    4. On error, produces an error message
    """
    producer = KafkaProducerManager()
    await producer.start()

    accumulated_content = ""
    seq = 0
    start_time = time.time()

    try:
        # Send metadata message first
        await producer.send_meta(
            request_id=request_id,
            model=model or settings.vllm_model or settings.ntqai_model,
            conversation_id=metadata.get("conversation_id") if metadata else None,
            kb_id=metadata.get("kb_id") if metadata else None,
            user_id=metadata.get("user_id") if metadata else None,
            metadata=metadata or {},
        )
        seq += 1

        # Prepare request to vLLM
        vllm_url = settings.vllm_base_url or settings.ntqai_base_url
        if not vllm_url:
            raise ValueError("vLLM base URL not configured")

        # Use OpenAI-compatible endpoint
        url = f"{vllm_url.rstrip('/')}/chat/completions"

        request_body = {
            "model": model or settings.vllm_model or settings.ntqai_model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }

        if max_tokens:
            request_body["max_tokens"] = max_tokens

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.vllm_api_key or settings.ntqai_api_key}",
        }

        prompt_tokens = 0
        completion_tokens = 0
        finish_reason = "stop"

        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream(
                "POST",
                url,
                json=request_body,
                headers=headers,
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    # Handle SSE format
                    if line.startswith("data: "):
                        data_str = line[6:]  # Remove "data: " prefix

                        if data_str.strip() == "[DONE]":
                            break

                        try:
                            data = json.loads(data_str)

                            # Extract delta content
                            choices = data.get("choices", [])
                            if choices:
                                choice = choices[0]
                                delta = choice.get("delta", {})
                                content = delta.get("content", "")

                                if content:
                                    accumulated_content += content

                                    # Send delta to Kafka
                                    await producer.send_delta(
                                        request_id=request_id,
                                        delta=content,
                                        seq=seq,
                                    )
                                    seq += 1

                                # Check for finish reason
                                if choice.get("finish_reason"):
                                    finish_reason = choice["finish_reason"]

                            # Extract usage if available
                            usage = data.get("usage", {})
                            if usage:
                                prompt_tokens = usage.get("prompt_tokens", 0)
                                completion_tokens = usage.get("completion_tokens", 0)

                        except json.JSONDecodeError as e:
                            logger.warning(f"Failed to parse SSE data: {e}")
                            continue

        # Send done message
        total_time = time.time() - start_time
        await producer.send_done(
            request_id=request_id,
            total_tokens=prompt_tokens + completion_tokens,
            completion_tokens=completion_tokens,
            prompt_tokens=prompt_tokens,
            finish_reason=finish_reason,
            final_content=accumulated_content,
            metadata={
                "processing_time": total_time,
                **(metadata or {}),
            },
            seq=seq,
        )

        logger.info(
            f"Completed streaming for request_id={request_id}, "
            f"tokens={completion_tokens}, time={total_time:.2f}s"
        )

        return {
            "status": "success",
            "request_id": request_id,
            "completion_tokens": completion_tokens,
            "prompt_tokens": prompt_tokens,
            "processing_time": total_time,
        }

    except httpx.HTTPStatusError as e:
        error_msg = f"HTTP error from vLLM: {e.response.status_code}"
        logger.error(f"Request {request_id}: {error_msg}")

        await producer.send_error(
            request_id=request_id,
            message=error_msg,
            error_code="http_error",
            details={"status_code": e.response.status_code},
            seq=seq,
        )

        return {
            "status": "error",
            "request_id": request_id,
            "error": error_msg,
        }

    except Exception as e:
        error_msg = str(e)
        logger.exception(f"Error streaming for request_id={request_id}: {error_msg}")

        await producer.send_error(
            request_id=request_id,
            message=error_msg,
            error_code="generation_error",
            seq=seq,
        )

        return {
            "status": "error",
            "request_id": request_id,
            "error": error_msg,
        }


async def _stream_with_langchain(
    request_id: str,
    messages: list[dict[str, Any]],
    conversation_id: Optional[str] = None,
    kb_id: Optional[str] = None,
    user_id: Optional[str] = None,
    agentic: bool = False,
    web_search: bool = False,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Stream using existing LangChain-based chat service and produce to Kafka.

    This integrates with the existing chat_service for RAG and agentic workflows.
    """

    from src.domain.schemas.chat import ChatRequest, Message, TextPart
    from src.services.chat_service import ChatService

    producer = KafkaProducerManager()
    await producer.start()

    accumulated_content = ""
    seq = 0
    start_time = time.time()

    try:
        # Convert messages to our format
        if not messages:
            raise ValueError("Messages list is empty")

        last_message = messages[-1]
        user_content = last_message.get("content", "")

        # Build message with metadata
        msg_metadata = {
            "conversation_id": conversation_id,
            "kb_id": kb_id,
            "user_id": user_id,
            **(metadata or {}),
        }

        user_message = Message(
            role="user",
            parts=[TextPart(type="text", text=user_content)],
            metadata=msg_metadata,
        )

        chat_request = ChatRequest(
            message=user_message,
            agentic=agentic,
            web_search=web_search,
        )

        # Send metadata message
        await producer.send_meta(
            request_id=request_id,
            model=settings.ntqai_model,
            conversation_id=conversation_id,
            kb_id=kb_id,
            user_id=user_id,
            metadata=msg_metadata,
        )
        seq += 1

        # Use chat service
        chat_service = ChatService()

        async for event in await chat_service.ask_sse(chat_request):
            if isinstance(event, str):
                # Parse SSE event
                if "event: message_delta" in event:
                    # Extract delta text from SSE
                    try:
                        lines = event.strip().split("\n")
                        for line in lines:
                            if line.startswith("data: "):
                                data = json.loads(line[6:])
                                delta = data.get("delta", {})
                                text = delta.get("text", "")

                                if text:
                                    accumulated_content += text
                                    await producer.send_delta(
                                        request_id=request_id,
                                        delta=text,
                                        seq=seq,
                                    )
                                    seq += 1
                    except (json.JSONDecodeError, KeyError):
                        pass

        # Send done message
        total_time = time.time() - start_time
        await producer.send_done(
            request_id=request_id,
            finish_reason="stop",
            final_content=accumulated_content,
            metadata={
                "processing_time": total_time,
                **(metadata or {}),
            },
            seq=seq,
        )

        logger.info(
            f"Completed LangChain streaming for request_id={request_id}, "
            f"time={total_time:.2f}s"
        )

        return {
            "status": "success",
            "request_id": request_id,
            "processing_time": total_time,
        }

    except Exception as e:
        error_msg = str(e)
        logger.exception(
            f"Error in LangChain streaming for request_id={request_id}: {error_msg}"
        )

        await producer.send_error(
            request_id=request_id,
            message=error_msg,
            error_code="generation_error",
            seq=seq,
        )

        return {
            "status": "error",
            "request_id": request_id,
            "error": error_msg,
        }


@shared_task(
    bind=True,
    name="tasks.generate_and_stream",
    soft_time_limit=10 * 60,  # 10 minutes
    time_limit=15 * 60,  # 15 minutes
    acks_late=True,
    track_started=True,
    max_retries=2,
    queue="llm_streaming",
)
def generate_and_stream(
    self: Task,
    request_id: str,
    messages: list[dict[str, Any]],
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    conversation_id: Optional[str] = None,
    kb_id: Optional[str] = None,
    user_id: Optional[str] = None,
    agentic: bool = False,
    web_search: bool = False,
    use_rag: bool = True,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Celery task that streams LLM responses to Kafka.

    Args:
        request_id: Unique identifier for this generation request
        messages: List of message dicts with 'role' and 'content'
        model: Model name to use
        temperature: Sampling temperature
        max_tokens: Maximum tokens to generate
        conversation_id: Optional conversation ID for context
        kb_id: Optional knowledge base ID for RAG
        user_id: User ID making the request
        agentic: Whether to use agentic workflow
        web_search: Whether to enable web search
        use_rag: Whether to use RAG (uses LangChain integration)
        metadata: Additional metadata

    Returns:
        Dict with status and details
    """
    logger.info(f"Starting generate_and_stream task for request_id={request_id}")

    try:
        self.update_state(
            state="PROGRESS",
            meta={
                "request_id": request_id,
                "status": StreamStatus.RUNNING.value,
            },
        )

        loop = get_or_create_eventloop()

        # Combine metadata
        full_metadata = {
            "conversation_id": conversation_id,
            "kb_id": kb_id,
            "user_id": user_id,
            **(metadata or {}),
        }

        if use_rag and kb_id:
            # Use LangChain integration with RAG
            result = loop.run_until_complete(
                _stream_with_langchain(
                    request_id=request_id,
                    messages=messages,
                    conversation_id=conversation_id,
                    kb_id=kb_id,
                    user_id=user_id,
                    agentic=agentic,
                    web_search=web_search,
                    metadata=full_metadata,
                )
            )
        else:
            # Direct vLLM streaming
            result = loop.run_until_complete(
                _stream_from_vllm(
                    request_id=request_id,
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    metadata=full_metadata,
                )
            )

        self.update_state(
            state="SUCCESS",
            meta={
                "request_id": request_id,
                "status": StreamStatus.DONE.value,
                "result": result,
            },
        )

        return result

    except SoftTimeLimitExceeded:
        logger.warning(f"Task timeout for request_id={request_id}")

        loop = get_or_create_eventloop()
        producer = KafkaProducerManager()
        loop.run_until_complete(producer.start())
        loop.run_until_complete(
            producer.send_error(
                request_id=request_id,
                message="Generation timeout",
                error_code="timeout",
            )
        )

        return {
            "status": "error",
            "request_id": request_id,
            "error": "timeout",
        }

    except Exception as e:
        logger.exception(f"Task error for request_id={request_id}: {e}")

        loop = get_or_create_eventloop()
        producer = KafkaProducerManager()
        loop.run_until_complete(producer.start())
        loop.run_until_complete(
            producer.send_error(
                request_id=request_id,
                message=str(e),
                error_code="task_error",
            )
        )

        return {
            "status": "error",
            "request_id": request_id,
            "error": str(e),
        }
