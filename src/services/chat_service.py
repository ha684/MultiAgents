# src/services/chat_service.py
import uuid
from typing import Any, AsyncGenerator, Dict, Generator, List, Union, cast

import tiktoken
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from qdrant_client.models import Filter, models

from src.agents.basic import (
    citation_agent,
    filename_agent,
    query_context_agent,
    response_agent,
    summary_agent,
)
from src.agents import Agent
from src.agents.com.stream_handler import AgenticStreamHandler
from src.common.streaming import StreamEventBuilder, StreamPhase
from src.common.types import Message, RetrievalContext, TextPart
from src.config.settings import settings
from src.exceptions.chat_exceptions import ValidationError
from src.models.chat import ChatRequest, SearchProvider, WebSearchConfig
from src.rag.vector import vector_retrieval
from src.services.conversation_service import ConversationService
from src.services.web_search_service import web_search_service
from src.tracking.observability import tracer
from src.utils.decorators import singleton
from src.utils.logger_conf import logger
from src.services.types import Conversation


@singleton
class ChatService:
    def __init__(self):
        self.conv_service = ConversationService()
        self.agent = Agent()
        self.tokenizer = tiktoken.encoding_for_model("gpt-4o")

    def _format_history(self, history: List[Message]) -> List[BaseMessage]:
        """Converts simple dict history to LangChain message objects with metadata preserved."""
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

    def sanitize_request(self, request: ChatRequest):
        """Sanitize the request"""
        if not request.message.metadata:
            raise ValidationError(message="Metadata is required")

        required_fields = ["conversation_id", "kb_id", "user_id"]

        metadata = request.message.metadata
        for field_name in required_fields:
            field_value = metadata.get(field_name)
            if not field_value:
                raise ValidationError(message=f"{field_name} is required")

            if field_name in ["conversation_id", "kb_id"]:
                if isinstance(field_value, str):
                    try:
                        uuid.UUID(field_value)
                    except ValueError:
                        raise ValidationError(
                            message=f"{field_name} must be a valid UUID"
                        )
                elif not isinstance(field_value, uuid.UUID):
                    raise ValidationError(message=f"{field_name} must be a valid UUID")

        return request

    async def _manage_conversation_length(
        self,
        conversation: List[BaseMessage],
        num_recent_messages: int,
        conversation_details: Conversation,
        user_id: str,
    ) -> List[BaseMessage]:
        """Manage conversation length using token counting and summarization."""
        min_messages_to_keep = 4
        max_conversation_tokens = 4096
        if len(conversation) <= min_messages_to_keep:
            return conversation
        total_tokens = summary_agent.count_tokens(conversation)

        if total_tokens <= max_conversation_tokens:
            return conversation

        start_index = 1 if isinstance(conversation[0], SystemMessage) else 0
        messages_to_summarize = conversation[start_index:-min_messages_to_keep]
        recent_messages = conversation[-min_messages_to_keep:]

        if messages_to_summarize:
            try:
                summary_obj = await summary_agent.summarize_conversation(
                    messages_to_summarize
                )
                new_summary_text = summary_obj.summary

                last_summarized_message_model = await self.conv_service.list_messages(
                    conversation_id=conversation_details.conversation_id,
                    last_summarized_order=num_recent_messages - min_messages_to_keep,
                )

                new_checkpoint_order = last_summarized_message_model[-1].metadata[
                    "message_order"
                ]

                conversation_obj = Conversation(
                    conversation_id=conversation_details.conversation_id,
                    is_active=True,
                    name=conversation_details.name,
                    summary=new_summary_text,
                    summarized_up_to_message_order=new_checkpoint_order,
                )
                await self.conv_service.update_conversation(
                    conversation=conversation_obj,
                    user_id=user_id,
                )

                return [
                    SystemMessage(content=f"Conversation Summary:\n{new_summary_text}")
                ] + recent_messages
            except Exception as e:
                logger.warning(f"Failed to summarize conversation: {e}")
                return recent_messages
        return conversation

    async def prepare_conversation(self, user_message: Message) -> List[BaseMessage]:
        """Prepare conversation history without saving the user message yet."""
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

            conversation_history.append(user_message)  # type: ignore
            formatted_conversation.extend(self._format_history(conversation_history))

            managed_conversation = await self._manage_conversation_length(
                conversation=formatted_conversation,
                num_recent_messages=len(conversation_history),
                conversation_details=conversation_details,
                user_id=user_id,
            )
            return managed_conversation

        except Exception as e:
            raise e

    async def _save_message_pair(
        self, user_message: Message, agent_message: Message, conversation_id: uuid.UUID
    ) -> None:
        """Save both user and agent messages in a single batch operation."""
        try:
            messages = [user_message, agent_message]
            await self.conv_service.add_messages(messages, conversation_id)
            logger.info(f"Saved message pair for conversation {conversation_id}")
        except Exception as e:
            logger.error(f"Error saving message pair: {e}")
            raise e

    async def _retrieve(
        self,
        conversation: List[BaseMessage],
        web_search_config: WebSearchConfig,
        metadata: Dict[str, Any],
    ) -> RetrievalContext:
        """Retrieves relevant documents based on the query and knowledge base ID."""
        embed_top = 50
        rerank_top = 20
        original_query = conversation[-1].content
        kb_id = metadata.get("kb_id")
        contextualized_query = original_query
        cited_docs = []
        retrieved_docs = []
        max_tokens = 8192

        logger.info(
            f"Retrieving documents for query: {original_query} in knowledgebase: {kb_id}"
        )
        with tracer.start_as_current_span("ChatAgent._retrieve") as span:
            if len(conversation) > 2:
                with tracer.start_as_current_span(
                    "QueryContextAgent.contextualize_query"
                ):
                    contextualized_query = await query_context_agent.ainvoke(
                        history=conversation
                    )
                    contextualized_query = contextualized_query.content
                span.set_attribute("contextualized_query", contextualized_query)
            if web_search_config.active:
                with tracer.start_as_current_span("search_service.search"):
                    retrieved_docs = await web_search_service.search(
                        query=contextualized_query,
                        provider=web_search_config.provider,
                        api_key=web_search_config.api_key,
                        max_results=rerank_top,
                    )
                    search_method = "web"
            else:
                with tracer.start_as_current_span("FilenameAgent.extract_filename"):
                    requested_filename = await filename_agent.ainvoke(
                        query=original_query
                    )

                filters: Filter = Filter(must=[])

                if requested_filename:
                    logger.info(f"Requested filename: {requested_filename}")
                    cast(List[models.Condition], filters.must).append(
                        models.FieldCondition(
                            key="metadata.original_filename",
                            match=models.MatchText(text=requested_filename),
                        )
                    )

                logger.info(f"Filter applied: {filters}")
                with tracer.start_as_current_span("vector_retrieval.retrieve"):
                    retrieved_docs = await vector_retrieval.retrieve(
                        kb_id=str(kb_id),
                        query=contextualized_query,
                        filters=filters,
                        top_k=embed_top,
                        top_n=rerank_top,
                    )
                    search_method = "rag"

            logger.info(
                f"Retrieved {len(retrieved_docs)} documents for query: {contextualized_query} in knowledgebase: {kb_id}"
            )
            span.set_attribute("retrieved_docs", len(retrieved_docs))
            if len(retrieved_docs) > rerank_top:
                retrieved_docs = retrieved_docs[:rerank_top]

            texts_list = [doc.page_content for doc in retrieved_docs]
            encoded_batches = self.tokenizer.encode_batch(
                text=texts_list, num_threads=4
            )
            total_tokens = sum(len(tokens) for tokens in encoded_batches)
            logger.info(
                f"Total retrieved documents tokens: {total_tokens} / {max_tokens}"
            )

            if total_tokens > max_tokens:
                final_docs = []
                current_tokens = 0
                for i, doc in enumerate(retrieved_docs):
                    doc_tokens = len(encoded_batches[i])
                    final_docs.append(doc)
                    current_tokens += doc_tokens

                    if current_tokens + doc_tokens > max_tokens and final_docs:
                        logger.warning(
                            f"Token limit ({max_tokens}) reached. "
                            f"Truncating context from {len(retrieved_docs)} to {len(final_docs)} documents."
                        )
                        break

                retrieved_docs = final_docs

            for i, doc in enumerate(retrieved_docs):
                doc.metadata["original_index"] = i

            if retrieved_docs:
                with tracer.start_as_current_span("CitationAgent.extract_citations"):
                    citation_indexes = await citation_agent.ainvoke(
                        history=conversation,
                        reference=retrieved_docs,
                    )
                if citation_indexes.indexes:
                    cited_docs = [
                        retrieved_docs[i - 1]
                        for i in citation_indexes.indexes
                        if 0 < i <= len(retrieved_docs)
                    ]
                logger.info(
                    f"Extracted {len(cited_docs)} citations for query: {original_query} in knowledgebase: {kb_id}"
                )

            retrieval_context = RetrievalContext(
                original_query=original_query,
                contextualized_query=contextualized_query,
                total_retrieved=len(retrieved_docs),
                total_cited=len(cited_docs),
                cited_chunks=cited_docs,
                search_method=search_method,
            )

            return retrieval_context

    async def _retrieve_stream(
        self,
        conversation: List[BaseMessage],
        web_search_config: WebSearchConfig,
        metadata: Dict[str, Any],
    ) -> Generator[Union[str, RetrievalContext], None, None]:
        """Retrieves relevant documents based on the query and knowledge base ID."""
        embed_top = 50
        rerank_top = 20
        original_query = conversation[-1].content
        kb_id = metadata.get("kb_id")
        contextualized_query = original_query
        cited_docs = []
        retrieved_docs = []
        max_tokens = 8192

        logger.info(
            f"Retrieving documents for query: {original_query} in knowledgebase: {kb_id}"
        )

        if len(conversation) > 2:
            yield StreamEventBuilder.status_update(
                StreamPhase.ANALYSIS,
                "Analyzing conversation context...",
                progress=0.1,
            )
            contextualized_query = await query_context_agent.ainvoke(
                history=conversation
            )
            contextualized_query = contextualized_query.content
        if web_search_config.active:
            yield StreamEventBuilder.status_update(
                StreamPhase.RETRIEVAL,
                "Performing web search...",
                progress=0.3,
                metadata={"provider": web_search_config.provider.value},
            )
            retrieved_docs = await web_search_service.search(
                query=contextualized_query,
                provider=web_search_config.provider,
                api_key=web_search_config.api_key,
                max_results=rerank_top,
            )

            urls = []
            favicons = []
            for doc in retrieved_docs:
                url = doc.metadata.get("original_filename", "")
                if url:
                    urls.append(url)
                favicon = doc.metadata.get("favicon", "")
                if favicon:
                    favicons.append(favicon)
            yield StreamEventBuilder.status_update(
                StreamPhase.RETRIEVAL,
                "Found web sources",
                progress=0.6,
                metadata={
                    "sources_count": len(retrieved_docs),
                    "urls": urls,
                    "favicons": favicons,
                },
            )
            search_method = "web"
        else:
            yield StreamEventBuilder.status_update(
                StreamPhase.RETRIEVAL,
                "Searching for relevant documents...",
                progress=0.3,
            )
            requested_filename = await filename_agent.ainvoke(query=original_query)

            filters: Filter = Filter(must=[])

            if requested_filename:
                logger.info(f"Requested filename: {requested_filename}")
                cast(List[models.Condition], filters.must).append(
                    models.FieldCondition(
                        key="metadata.original_filename",
                        match=models.MatchText(text=requested_filename),
                    )
                )

            retrieved_docs = await vector_retrieval.retrieve(
                kb_id=str(kb_id),
                query=contextualized_query,
                filters=filters,
                top_k=embed_top,
                top_n=rerank_top,
            )
            search_method = "rag"
            yield StreamEventBuilder.status_update(
                StreamPhase.RETRIEVAL,
                "Found relevant documents",
                progress=0.6,
                metadata={"sources_count": len(retrieved_docs)},
            )

        if len(retrieved_docs) > rerank_top:
            retrieved_docs = retrieved_docs[:rerank_top]

        texts_list = [doc.page_content for doc in retrieved_docs]
        encoded_batches = self.tokenizer.encode_batch(text=texts_list, num_threads=4)
        total_tokens = sum(len(tokens) for tokens in encoded_batches)
        logger.info(f"Total retrieved documents tokens: {total_tokens} / {max_tokens}")

        if total_tokens > max_tokens:
            final_docs = []
            current_tokens = 0
            for i, doc in enumerate(retrieved_docs):
                doc_tokens = len(encoded_batches[i])
                final_docs.append(doc)
                current_tokens += doc_tokens

                if current_tokens + doc_tokens > max_tokens and final_docs:
                    logger.warning(
                        f"Token limit ({max_tokens}) reached. "
                        f"Truncating context from {len(retrieved_docs)} to {len(final_docs)} documents."
                    )
                    break

            retrieved_docs = final_docs

        if retrieved_docs:
            yield StreamEventBuilder.status_update(
                StreamPhase.PROCESSING,
                "Extracting relevant citations...",
                progress=0.8,
            )
            citation_indexes = await citation_agent.ainvoke(
                history=conversation,
                reference=retrieved_docs,
            )
            if citation_indexes.indexes:
                for i in citation_indexes.indexes:
                    if 0 < i <= len(retrieved_docs):
                        retrieved_docs[i - 1].metadata["original_index"] = i
                        cited_docs.append(retrieved_docs[i - 1])

            yield StreamEventBuilder.status_update(
                StreamPhase.PROCESSING,
                "Extracted relevant citations",
                progress=1.0,
                metadata={"sources_count": len(cited_docs)},
            )
        retrieval_context = RetrievalContext(
            original_query=original_query,
            contextualized_query=contextualized_query,
            total_retrieved=len(retrieved_docs),
            total_cited=len(cited_docs),
            cited_chunks=cited_docs,
            search_method=search_method,
        )
        yield retrieval_context

    async def ask_normal(
        self,
        user_message: Message,
        conversation: List[BaseMessage],
        web_search_config: WebSearchConfig,
        metadata: Dict[str, Any],
    ) -> Message:
        """Handles non-streaming (full text) response."""
        try:
            retrieval_context = await self._retrieve(
                conversation, web_search_config, metadata
            )
            with tracer.start_as_current_span("ResponseAgent.generate_response"):
                response = await response_agent.ainvoke(
                    contexts=retrieval_context.cited_chunks,
                    history=conversation,
                )
                response_dict = response.model_dump()

            if web_search_config.active:
                response_dict["response_metadata"]["search_method"] = "web_search"
            else:
                response_dict["response_metadata"]["search_method"] = "database_search"

            clean_metadata = metadata.copy()
            if "web_search_config" in clean_metadata:
                web_config_copy = clean_metadata["web_search_config"].copy()
                web_config_copy.pop("api_key", None)
                clean_metadata["web_search_config"] = web_config_copy

            response_dict["response_metadata"].update(clean_metadata)

            agent_message = Message(
                role="agent",
                parts=[TextPart(type="text", text=response_dict["content"])],
                metadata=response_dict["response_metadata"],
                retrieval_context=retrieval_context,
            )

            await self._save_message_pair(
                user_message, agent_message, metadata.get("conversation_id")
            )

            return agent_message

        except Exception as e:
            logger.error(f"Error in ask_normal: {e}")
            raise e

    async def ask_stream(
        self,
        user_message: Message,
        conversation: List[BaseMessage],
        web_search_config: WebSearchConfig,
        metadata: Dict[str, Any],
    ) -> AsyncGenerator[str | BaseMessage, None]:
        """Handles streaming response with robust error handling."""
        try:
            yield StreamEventBuilder.message_start()

            retrieve_generator = self._retrieve_stream(
                conversation, web_search_config, metadata
            )
            retrieval_context = None

            async for event in retrieve_generator:
                if isinstance(event, RetrievalContext):
                    retrieval_context = event
                else:
                    yield event

            yield StreamEventBuilder.status_update(
                StreamPhase.PROCESSING, "Generating response...", progress=0.0
            )

            response_generator = response_agent.astream(
                contexts=retrieval_context.cited_chunks,
                history=conversation,
            )

            i = 0
            final_response = None
            async for chunk in response_generator:
                if isinstance(chunk, str) and chunk != "error":
                    yield StreamEventBuilder.content_delta(chunk, index=i)
                    i += 1
                elif isinstance(chunk, dict):
                    final_response = chunk
                    break
                else:
                    yield StreamEventBuilder.error(
                        "LLM issue", "Error while streaming response", code=500
                    )

            yield StreamEventBuilder.status_update(
                StreamPhase.COMPLETE, "Response generation complete", progress=1.0
            )

            references = [doc.model_dump() for doc in retrieval_context.cited_chunks]

            if web_search_config.active:
                final_metadata = {"search_method": "web_search"}
                final_metadata.update(metadata)
                response_metadata = final_response.get("response_metadata")
                final_metadata.update(response_metadata)
            else:
                final_metadata = {"search_method": "database_search"}
                final_metadata.update(metadata)
                response_metadata = final_response.get("response_metadata")
                final_metadata.update(response_metadata)

            agent_message = Message(
                role="agent",
                parts=[TextPart(type="text", text=final_response.get("content"))],
                metadata=final_metadata,
                retrieval_context=retrieval_context,
            )

            # Save both messages together
            await self._save_message_pair(
                user_message, agent_message, metadata.get("conversation_id")
            )

            yield StreamEventBuilder.message_stop(
                references=references,
                metadata=final_metadata,
            )

        except Exception as e:
            logger.exception(
                f"An error occurred during the streaming chat response: {e}"
            )
            yield StreamEventBuilder.error(
                error_type="generation_error",
                message=f"An internal error occurred: {str(e)}",
                code=500,
            )

    async def _stream_agentic_workflow(
        self,
        user_message: Message,
        conversation: List[BaseMessage],
        metadata: Dict[str, Any],
    ) -> AsyncGenerator[str, None]:
        """Stream agentic workflow with clean, focused updates"""
        try:
            yield StreamEventBuilder.message_start()
            handler = AgenticStreamHandler()
            final_state = None
            conversation_id = metadata.get("conversation_id")

            async for event in self.agent.stream(conversation):
                result = await handler.handle_event(event)

                if result:
                    yield result

                if (
                    event["event"] == "on_chain_end"
                    and event.get("name") == "MainOrchestrator"
                ):
                    final_state = event.get("data", {}).get("output")

                if (
                    event["event"] == "on_chain_end"
                    and event["name"] != "MainOrchestrator"
                ):
                    node_output = event.get("data", {}).get("output")
                    if node_output:
                        last_known_state = node_output

            if not final_state:
                final_state = last_known_state

            yield StreamEventBuilder.status_update(
                StreamPhase.COMPLETE,
                "Response complete",
            )

            response_metadata = final_state.get("response_metadata", {})
            retrieval_contexts = final_state.get("retrieval_contexts", {})

            cited_chunks = retrieval_contexts.get("cited_chunks", [])
            if not cited_chunks:
                cited_chunks = final_state.get("cited_documents", [])

            references = [
                doc.model_dump() if hasattr(doc, "model_dump") else doc
                for doc in cited_chunks
            ]

            agent_message = Message(
                role="agent",
                parts=[TextPart(type="text", text=final_state["final_answer"])],
                metadata=response_metadata,
                retrieval_context=RetrievalContext(
                    original_query=retrieval_contexts.get(
                        "original_query", conversation[-1].content
                    ),
                    contextualized_query=retrieval_contexts.get(
                        "contextualized_query", ""
                    ),
                    total_retrieved=retrieval_contexts.get("total_retrieved", 0),
                    total_cited=len(cited_chunks),
                    cited_chunks=cited_chunks,
                    search_method=retrieval_contexts.get("search_method", "rag"),
                ),
            )

            await self._save_message_pair(user_message, agent_message, conversation_id)

            yield StreamEventBuilder.message_stop(
                references=references,
                metadata=response_metadata,
            )

        except Exception as e:
            logger.exception(f"Error in agentic workflow streaming: {e}")
            yield StreamEventBuilder.error(
                error_type="agentic_workflow_error",
                message=f"An error occurred: {str(e)}",
                code=500,
            )

    async def ask(self, request: ChatRequest) -> Message:
        """Process a chat request and return a response."""
        with tracer.start_as_current_span("ChatService.ask") as span:
            span.set_attribute("user.id", request.message.metadata.get("user_id"))
            span.set_attribute("kb.id", request.message.metadata.get("kb_id"))
            request = self.sanitize_request(request)
            web_search_config = _setup_web_search_config(request)

            metadata = request.message.metadata
            metadata.update({"web_search_config": web_search_config.model_dump()})

            conversation = await self.prepare_conversation(request.message)
            conversation[-1].additional_kwargs["message_metadata"] = metadata

            if request.agentic:
                response = await self.agent.ainvoke(conversation)
                await self._save_message_pair(
                    request.message, response, metadata.get("conversation_id")
                )
            else:
                response = await self.ask_normal(
                    request.message, conversation, web_search_config, metadata
                )
            return response

    async def ask_sse(
        self, request: ChatRequest
    ) -> AsyncGenerator[str | BaseMessage, None]:
        """Process a chat request and return a streaming response."""
        request = self.sanitize_request(request)
        web_search_config = _setup_web_search_config(request)

        metadata = request.message.metadata
        metadata.update({"web_search_config": web_search_config.model_dump()})

        conversation = await self.prepare_conversation(request.message)
        conversation[-1].additional_kwargs["message_metadata"] = metadata

        if request.agentic:
            response = self._stream_agentic_workflow(
                request.message, conversation, metadata
            )
        else:
            response = self.ask_stream(
                request.message, conversation, web_search_config, metadata
            )
        return response


def _get_api_key_for_provider(provider: SearchProvider) -> str:
    """Get API key based on the selected provider."""
    if provider == SearchProvider.TAVILY.value:
        return settings.tavily_api_key
    elif provider == SearchProvider.FIRECRAWL.value:
        return settings.firecrawl_api_key
    else:
        return ""


def _setup_web_search_config(request: ChatRequest) -> WebSearchConfig:
    """Setup web search config based on the request."""
    if settings.enable_websearch and request.web_search:
        web_search_config = WebSearchConfig(
            provider=settings.websearch_provider,
            active=True,
            api_key=_get_api_key_for_provider(settings.websearch_provider),
        )
    else:
        web_search_config = WebSearchConfig(active=False)
    return web_search_config
