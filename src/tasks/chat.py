# src/tasks/chat.py
"""
Celery Task for Chat Inference

This task handles LLM inference with streaming support:
- Publishes tokens to Redis Stream for real-time delivery
- Supports cancellation via Redis flag
- Saves final result to PostgreSQL
- Preserves thinking content for agent mode
"""

import asyncio
import json
import uuid
from typing import Any

from celery import Task, shared_task
from celery.exceptions import SoftTimeLimitExceeded
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from src.agents import Agent
from src.agents.basic import (
    citation_agent,
    query_context_agent,
    response_agent,
)
from src.core.config.graph_configs import GRAPH_CONFIGS
from src.core.config.settings import settings
from src.domain.schemas.chat import (
    Message,
    RetrievalContext,
    TextPart,
)
from src.domain.schemas.chat_task import ChatTaskStatus
from src.domain.schemas.stream import StreamPhase
from src.infrastructure.tasks.stream_buffer import (
    chat_stream_buffer,
)
from src.rag.vectorstores import vector_retrieval
from src.services.conversation_service import ConversationService
from src.services.web_search_service import web_search_service
from src.utils.logger_conf import logger

# Global event loop for worker process
_loop = None


def get_or_create_eventloop():
    """Get or create event loop for current worker process"""
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop


class ChatInferenceTask:
    """
    Handles the actual chat inference logic with streaming to Redis.

    Separated from the Celery task decorator for better testability.
    """

    def __init__(self):
        self.agent = Agent()
        self.conv_service = ConversationService()
        self.stream_buffer = chat_stream_buffer

    async def run(
        self,
        task_id: str,
        conversation_id: str,
        user_id: str,
        kb_id: str,
        message_text: str,
        message_metadata: dict[str, Any],
        agentic: bool = False,
        web_search_active: bool = False,
        web_search_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Execute chat inference with streaming to Redis.

        Returns:
            Dictionary with task result
        """
        try:
            # Initialize task in Redis
            await self.stream_buffer.init_task(
                task_id=task_id,
                conversation_id=conversation_id,
                user_id=user_id,
                kb_id=kb_id,
                metadata={"agentic": agentic},
            )

            # Set status to streaming
            await self.stream_buffer.set_status(task_id, ChatTaskStatus.STREAMING)
            await self.stream_buffer.publish_event(
                task_id,
                "message_start",
                {"message": "Message generation started"},
            )

            # Build user message
            user_message = Message(
                role="user",
                parts=[TextPart(type="text", text=message_text)],
                metadata={
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                    "kb_id": kb_id,
                    **message_metadata,
                },
            )

            # Prepare conversation history
            conversation = await self._prepare_conversation(user_message)
            conversation[-1].additional_kwargs["message_metadata"] = message_metadata

            if agentic:
                result = await self._run_agentic_workflow(
                    task_id,
                    user_message,
                    conversation,
                    message_metadata,
                )
            else:
                result = await self._run_standard_workflow(
                    task_id,
                    user_message,
                    conversation,
                    kb_id,
                    web_search_active,
                    web_search_config or {},
                    message_metadata,
                )

            # Set completion status
            await self.stream_buffer.set_status(task_id, ChatTaskStatus.COMPLETE)

            return result

        except Exception as e:
            logger.exception(f"Error in chat inference task {task_id}: {e}")
            await self.stream_buffer.publish_error(
                task_id,
                "inference_error",
                str(e),
                code=500,
            )
            await self.stream_buffer.set_status(task_id, ChatTaskStatus.ERROR)
            return {
                "status": "error",
                "task_id": task_id,
                "error": str(e),
            }

    async def _prepare_conversation(self, user_message: Message) -> list[BaseMessage]:
        """Prepare conversation history."""
        conversation_id = user_message.metadata.get("conversation_id")
        user_id = user_message.metadata.get("user_id")

        try:
            conversation_details = await self.conv_service.get_conversation(
                conversation_id, user_id
            )
            last_summarized_order = conversation_details.summarized_up_to_message_order

            conversation_history = await self.conv_service.list_messages(
                conversation_id, last_summarized_order
            )

            summary_text = conversation_details.summary
            formatted_conversation = []
            if summary_text:
                formatted_conversation.append(
                    SystemMessage(content=f"Conversation Summary:\n{summary_text}")
                )

            conversation_history.append(user_message)
            formatted_conversation.extend(self._format_history(conversation_history))

            return formatted_conversation

        except Exception as e:
            logger.error(f"Error preparing conversation: {e}")
            return [HumanMessage(content=user_message.parts[0].text)]

    def _format_history(self, history: list[Message]) -> list[BaseMessage]:
        """Convert message history to LangChain format."""
        formatted_messages = []
        for item in history:
            if item.role not in ("user", "agent"):
                continue

            content = item.parts[0].text
            metadata = item.metadata or {}

            if item.role == "user":
                msg = HumanMessage(
                    content=content, additional_kwargs={"message_metadata": metadata}
                )
            else:
                msg = AIMessage(
                    content=content, additional_kwargs={"message_metadata": metadata}
                )

            formatted_messages.append(msg)

        return formatted_messages

    async def _run_standard_workflow(
        self,
        task_id: str,
        user_message: Message,
        conversation: list[BaseMessage],
        kb_id: str,
        web_search_active: bool,
        web_search_config: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Run standard (non-agentic) chat workflow with streaming."""

        if await self.stream_buffer.is_cancelled(task_id):
            return {"status": "cancelled", "task_id": task_id}

        await self.stream_buffer.publish_status(
            task_id,
            StreamPhase.RETRIEVAL.value,
            "Searching for relevant documents...",
            0.3,
        )

        retrieval_context = await self._retrieve(
            conversation,
            kb_id,
            web_search_active,
            web_search_config,
            task_id,
        )

        if await self.stream_buffer.is_cancelled(task_id):
            return {"status": "cancelled", "task_id": task_id}

        await self.stream_buffer.publish_status(
            task_id, StreamPhase.PROCESSING.value, "Generating response...", 0.5
        )

        response_generator = response_agent.astream(
            contexts=retrieval_context.cited_chunks,
            history=conversation,
        )

        accumulated_content = ""
        index = 0
        final_response = None

        async for chunk in response_generator:
            if index % 10 == 0:
                if await self.stream_buffer.is_cancelled(task_id):
                    return {"status": "cancelled", "task_id": task_id}

            if isinstance(chunk, str) and chunk != "error":
                accumulated_content += chunk
                await self.stream_buffer.publish_content_delta(task_id, chunk, index)
                index += 1
            elif isinstance(chunk, dict):
                final_response = chunk
                break

        if not final_response:
            final_response = {"content": accumulated_content, "response_metadata": {}}

        references = [doc.model_dump() for doc in retrieval_context.cited_chunks]

        search_method = "web_search" if web_search_active else "database_search"
        final_metadata = {"search_method": search_method}
        final_metadata.update(metadata)
        if final_response.get("response_metadata"):
            final_metadata.update(final_response["response_metadata"])

        agent_message = Message(
            role="agent",
            parts=[TextPart(type="text", text=final_response.get("content", ""))],
            metadata=final_metadata,
            retrieval_context=retrieval_context,
        )

        conversation_id_str = user_message.metadata.get("conversation_id")
        if not conversation_id_str:
            raise ValueError("conversation_id not found in user_message metadata")
        await self._save_message_pair(user_message, agent_message, conversation_id_str)
        await self.stream_buffer.publish_complete(task_id, references, final_metadata)
        await self.stream_buffer.cleanup_task(task_id)
        return {
            "status": "success",
            "task_id": task_id,
            "content_length": len(accumulated_content),
            "references_count": len(references),
        }

    async def _run_agentic_workflow(
        self,
        task_id: str,
        user_message: Message,
        conversation: list[BaseMessage],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Run agentic workflow with streaming."""

        accumulated_thinking = ""
        accumulated_content = ""
        content_index = 0
        thinking_index = 0
        final_state = None
        last_known_state = None

        current_graph = None
        # current_node = None
        graph_stack = []
        last_phase = None
        tool_args_buffer = {}
        thought_extracted_length = {}

        async for event in self.agent.astream(conversation):
            if thinking_index % 20 == 0 or content_index % 10 == 0:
                if await self.stream_buffer.is_cancelled(task_id):
                    return {"status": "cancelled", "task_id": task_id}

            kind = event["event"]
            name = event.get("name", "")

            if kind == "on_chain_start":
                if name in GRAPH_CONFIGS:
                    graph_stack.append(name)
                    current_graph = name
                elif current_graph:
                    config = GRAPH_CONFIGS.get(current_graph)
                    if config:
                        node_meta = config.get_node_meta(name)
                        if node_meta:
                            # current_node = name
                            last_phase = node_meta.stream_phase
                            if node_meta.show_in_ui:
                                await self.stream_buffer.publish_status(
                                    task_id,
                                    node_meta.stream_phase.value,
                                    node_meta.display_message,
                                )

            elif kind == "on_chain_end":
                if name in GRAPH_CONFIGS:
                    if graph_stack:
                        graph_stack.pop()
                    current_graph = graph_stack[-1] if graph_stack else None

                output = event.get("data", {}).get("output")
                if output:
                    last_known_state = output

                if event.get("name") == "MainGraph":
                    final_state = event.get("data", {}).get("output")

            elif kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]

                if last_phase == StreamPhase.SYNTHESIS:
                    if chunk.content:
                        accumulated_content += chunk.content
                        await self.stream_buffer.publish_content_delta(
                            task_id, chunk.content, content_index
                        )
                        content_index += 1
                else:
                    if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                        for tc in chunk.tool_call_chunks:
                            args = tc.get("args", "")
                            if not args:
                                continue

                            tc_id = tc.get("id", "default")
                            if tc_id not in tool_args_buffer:
                                tool_args_buffer[tc_id] = ""
                                thought_extracted_length[tc_id] = 0

                            tool_args_buffer[tc_id] += args

                            new_text = self._extract_incremental_thinking(
                                tc_id, tool_args_buffer, thought_extracted_length
                            )

                            if new_text:
                                accumulated_thinking += new_text
                                await self.stream_buffer.publish_thinking_delta(
                                    task_id, new_text, thinking_index
                                )
                                thinking_index += 1

        if not final_state:
            final_state = last_known_state or {}

        final_answer = final_state.get("final_answer", accumulated_content)
        response_metadata = final_state.get("response_metadata", {})
        cited_documents = final_state.get("cited_documents", [])

        references = [
            doc.model_dump() if hasattr(doc, "model_dump") else doc
            for doc in cited_documents
        ]

        conversation_id_str = user_message.metadata.get("conversation_id")
        if not conversation_id_str:
            raise ValueError("conversation_id not found in user_message metadata")

        agent_message = Message(
            role="agent",
            parts=[TextPart(type="text", text=final_answer)],
            metadata=response_metadata,
            retrieval_context=RetrievalContext(
                total_retrieved=len(cited_documents),
                total_cited=len(cited_documents),
                cited_chunks=cited_documents,
            ),
        )

        await self._save_message_pair(user_message, agent_message, conversation_id_str)

        await self.stream_buffer.publish_complete(
            task_id, references, response_metadata
        )

        await self.stream_buffer.cleanup_task(task_id)

        return {
            "status": "success",
            "task_id": task_id,
            "content_length": len(final_answer),
            "thinking_length": len(accumulated_thinking),
            "references_count": len(references),
        }

    def _extract_incremental_thinking(
        self,
        tool_call_id: str,
        buffer: dict[str, str],
        extracted_length: dict[str, int],
    ) -> str | None:
        """Extract NEW thinking text from buffered JSON."""
        buf = buffer.get(tool_call_id, "")
        previously_extracted = extracted_length.get(tool_call_id, 0)

        if not buf:
            return None

        try:
            parsed = json.loads(buf)
            if isinstance(parsed, dict):
                thought_text = parsed.get("thought") or parsed.get("thinking") or ""
                if thought_text and len(thought_text) > previously_extracted:
                    new_text = thought_text[previously_extracted:]
                    extracted_length[tool_call_id] = len(thought_text)
                    return new_text
        except json.JSONDecodeError:
            import re

            pattern = (
                r'["\'](?:thought|thinking)["\']:\s*["\']([^"\'\\]*(?:\\.[^"\'\\]*)*)'
            )
            match = re.search(pattern, buf, re.IGNORECASE | re.DOTALL)

            if match:
                thought_text = match.group(1)
                thought_text = (
                    thought_text.replace('\\"', '"')
                    .replace("\\n", "\n")
                    .replace("\\t", "\t")
                )

                if len(thought_text) > previously_extracted:
                    new_text = thought_text[previously_extracted:]
                    extracted_length[tool_call_id] = len(thought_text)
                    return new_text

        return None

    async def _retrieve(
        self,
        conversation: list[BaseMessage],
        kb_id: str,
        web_search_active: bool,
        web_search_config: dict[str, Any],
        task_id: str,
    ) -> RetrievalContext:
        """Retrieve relevant documents."""
        embed_top = 50
        rerank_top = 15
        original_query = conversation[-1].content
        contextualized_query = original_query

        if len(conversation) > 2:
            await self.stream_buffer.publish_status(
                task_id,
                StreamPhase.ANALYSIS.value,
                "Analyzing conversation context...",
                0.1,
            )
            result = await query_context_agent.ainvoke(history=conversation)
            contextualized_query = result.content

        if web_search_active:
            await self.stream_buffer.publish_status(
                task_id,
                StreamPhase.RETRIEVAL.value,
                "Performing web search...",
                0.3,
            )
            provider = web_search_config.get("provider", "tavily")
            api_key = web_search_config.get("api_key", settings.tavily_api_key)
            retrieved_docs = await web_search_service.search(
                query=contextualized_query,
                provider=provider,
                api_key=api_key,
                max_results=rerank_top,
            )
            search_method = "web"
        else:
            retrieved_docs = await vector_retrieval.retrieve(
                kb_id=kb_id,
                query=contextualized_query,
                filters=None,
                top_k=embed_top,
                top_n=rerank_top,
            )
            search_method = "rag"

        await self.stream_buffer.publish_status(
            task_id,
            StreamPhase.RETRIEVAL.value,
            f"Found {len(retrieved_docs)} relevant sources",
            0.6,
            metadata={"sources_count": len(retrieved_docs)},
        )

        if len(retrieved_docs) > rerank_top:
            retrieved_docs = retrieved_docs[:rerank_top]

        cited_docs = []
        if retrieved_docs:
            await self.stream_buffer.publish_status(
                task_id,
                StreamPhase.PROCESSING.value,
                "Extracting relevant citations...",
                0.8,
            )
            citation_indexes = await citation_agent.ainvoke(
                query=contextualized_query,
                reference=retrieved_docs,
            )
            if citation_indexes.indexes:
                for i in citation_indexes.indexes:
                    if 0 < i <= len(retrieved_docs):
                        retrieved_docs[i - 1].metadata["original_index"] = i
                        cited_docs.append(retrieved_docs[i - 1])

        return RetrievalContext(
            original_query=original_query,
            contextualized_query=contextualized_query,
            total_retrieved=len(retrieved_docs),
            total_cited=len(cited_docs),
            cited_chunks=cited_docs,
            search_method=search_method,
        )

    async def _save_message_pair(
        self, user_message: Message, agent_message: Message, conversation_id: uuid.UUID
    ) -> None:
        """Save both user and agent messages."""
        try:
            messages = [user_message, agent_message]
            await self.conv_service.add_messages(messages, conversation_id)
        except Exception as e:
            logger.error(f"Error saving message pair: {e}")


_chat_inference_task = None


def get_chat_inference_task() -> ChatInferenceTask:
    """Get or create the chat inference task handler."""
    global _chat_inference_task
    if _chat_inference_task is None:
        _chat_inference_task = ChatInferenceTask()
    return _chat_inference_task


@shared_task(
    bind=True,
    name="tasks.chat_inference",
    soft_time_limit=10 * 60,
    time_limit=12 * 60,
    acks_late=True,
    track_started=True,
    queue="chat_inference",
)
def chat_inference(
    self: Task,
    task_id: str,
    conversation_id: str,
    user_id: str,
    kb_id: str,
    message_text: str,
    message_metadata: dict[str, Any],
    agentic: bool = False,
    web_search_active: bool = False,
    web_search_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Celery task for chat inference.

    This task runs the LLM inference and streams results to Redis.
    Clients can subscribe to the Redis stream to receive real-time updates.

    Args:
        task_id: Pre-generated task ID for tracking
        conversation_id: The conversation ID
        user_id: The user ID
        kb_id: The knowledge base ID
        message_text: The user's message
        message_metadata: Additional metadata
        agentic: Whether to use agentic workflow
        web_search_active: Whether web search is enabled
        web_search_config: Web search configuration

    Returns:
        Dictionary with task result
    """
    try:
        self.update_state(
            state="PROGRESS",
            meta={"current": 0, "total": 100, "status": "Starting inference..."},
        )

        loop = get_or_create_eventloop()
        handler = get_chat_inference_task()

        result = loop.run_until_complete(
            handler.run(
                task_id=task_id,
                conversation_id=conversation_id,
                user_id=user_id,
                kb_id=kb_id,
                message_text=message_text,
                message_metadata=message_metadata,
                agentic=agentic,
                web_search_active=web_search_active,
                web_search_config=web_search_config,
            )
        )

        self.update_state(
            state="SUCCESS",
            meta={"current": 100, "total": 100, "result": result},
        )

        return result

    except SoftTimeLimitExceeded:
        logger.warning(f"Chat inference task {task_id} exceeded time limit")
        loop = get_or_create_eventloop()
        loop.run_until_complete(
            chat_stream_buffer.publish_error(
                task_id, "timeout", "Task exceeded time limit", code=408
            )
        )
        loop.run_until_complete(
            chat_stream_buffer.set_status(task_id, ChatTaskStatus.ERROR)
        )
        return {
            "status": "timeout",
            "task_id": task_id,
            "error": "Task exceeded time limit",
        }

    except Exception as e:
        logger.exception(f"Error in chat inference task {task_id}: {e}")
        loop = get_or_create_eventloop()
        loop.run_until_complete(
            chat_stream_buffer.publish_error(
                task_id, "inference_error", str(e), code=500
            )
        )
        loop.run_until_complete(
            chat_stream_buffer.set_status(task_id, ChatTaskStatus.ERROR)
        )
        return {
            "status": "error",
            "task_id": task_id,
            "error": str(e),
        }
