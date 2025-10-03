import uuid
from typing import Any, AsyncGenerator, Dict, Generator, List, Tuple, Union, cast

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from qdrant_client.models import Filter, models

from src.agents.researcher.main_agent import AgentInputState, MainAgent
from src.agents.basic import (
    citation_agent,
    filename_agent,
    query_context_agent,
    response_agent,
    summary_agent,
)
from src.common.streaming import StreamEventBuilder, StreamPhase
from src.common.types import Message, RetrievalContext, TextPart
from src.config.settings import settings
from src.exceptions.chat_exceptions import ConversationNotFoundError, ValidationError
from src.models.chat import ChatRequest, SearchProvider, WebSearchConfig
from src.rag.vector import vector_retrieval
from src.services.conversation_service import ConversationService
from src.services.web_search_service import web_search_service
from src.tracking.observability import tracer
from src.utils.decorators import singleton
from src.utils.logger_conf import logger
from src.agents.main import OrchestratorGraph
import tiktoken
from src.db.models.conversation import MessageStatus


@singleton
class ChatService:
    def __init__(self):
        self.conv_service = ConversationService()
        self.orchestrator_graph = OrchestratorGraph()
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
        self, conversation: List[BaseMessage]
    ) -> List[BaseMessage]:
        """Manage conversation length using token counting and summarization."""
        min_messages_to_keep = 4
        max_conversation_tokens = 8192
        if len(conversation) <= min_messages_to_keep:
            return conversation
        total_tokens = summary_agent.count_tokens(conversation)

        if total_tokens <= max_conversation_tokens:
            return conversation

        if total_tokens > max_conversation_tokens:
            messages_to_keep = max(min_messages_to_keep, len(conversation) // 3)
            recent_messages = conversation[-messages_to_keep:]

            messages_to_summarize = conversation[:-messages_to_keep]

            if messages_to_summarize:
                try:
                    summary = await summary_agent.summarize_conversation(
                        messages_to_summarize
                    )

                    if recent_messages and isinstance(
                        recent_messages[-1], HumanMessage
                    ):
                        recent_messages[-1] = (
                            summary_agent.append_summary_to_user_message(
                                recent_messages[-1], summary
                            )
                        )

                    return recent_messages
                except Exception as e:
                    logger.warning(f"Failed to summarize conversation: {e}")
                    return recent_messages
        return conversation

    async def sanitize_message(self, message: Message) -> List[BaseMessage]:
        """Sanitize the message and manage conversation length."""
        conversation_id = message.metadata.get("conversation_id")
        user_id = message.metadata.get("user_id")
        try:
            conversation_history = await self.conv_service.list_messages(
                conversation_id, user_id
            )
            if conversation_history is None:
                raise ConversationNotFoundError(conversation_id=conversation_id)
            message_id = await self.conv_service.add_message(message, conversation_id)
            message.metadata["message_id"] = message_id
            conversation_history.append(message)  # type: ignore
            formatted_conversation = self._format_history(conversation_history)
            managed_conversation = await self._manage_conversation_length(
                formatted_conversation
            )
            return managed_conversation

        except Exception as e:
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
                span.set_attribute("contextualized_query", contextualized_query)
            if web_search_config.active:
                with tracer.start_as_current_span("search_service.search"):
                    retrieved_docs = await web_search_service.search(
                        query=contextualized_query,
                        provider=web_search_config.provider,
                        api_key=web_search_config.api_key,
                        max_results=rerank_top,
                    )
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
                StreamPhase.CONTEXT_ANALYSIS,
                "Analyzing conversation context...",
                progress=0.1,
            )
            contextualized_query = await query_context_agent.ainvoke(
                history=conversation
            )
            logger.info(f"Contextualized query: {contextualized_query}")

        if web_search_config.active:
            yield StreamEventBuilder.status_update(
                StreamPhase.WEB_SEARCH,
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
            for doc in retrieved_docs:
                url = doc.metadata.get("original_filename", "")
                if url:
                    urls.append(url)

            yield StreamEventBuilder.status_update(
                StreamPhase.WEB_SEARCH,
                "Found web sources",
                progress=0.6,
                metadata={"sources_count": len(retrieved_docs), "urls": urls},
            )
        else:
            yield StreamEventBuilder.status_update(
                StreamPhase.DOCUMENT_RETRIEVAL,
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

            logger.info(f"Filter applied: {filters}")
            retrieved_docs = await vector_retrieval.retrieve(
                kb_id=str(kb_id),
                query=contextualized_query,
                filters=filters,
                top_k=embed_top,
                top_n=rerank_top,
            )
            yield StreamEventBuilder.status_update(
                StreamPhase.DOCUMENT_RETRIEVAL,
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
                StreamPhase.CITATION_EXTRACTION,
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
                StreamPhase.CITATION_EXTRACTION,
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
        )
        yield retrieval_context

    async def ask_normal(
        self,
        conversation: List[BaseMessage],
        web_search_config: WebSearchConfig,
        metadata: Dict[str, Any],
    ) -> Tuple[Message, List[Dict]]:
        """Handles non-streaming (full text) response."""
        user_message_id = _extract_message_id(conversation[-1])

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
            response_dict["response_metadata"].update(metadata)

            message = Message(
                role="agent",
                parts=[TextPart(type="text", text=response_dict["content"])],
                metadata=response_dict["response_metadata"],
                retrieval_context=retrieval_context,
            )

            await self.conv_service.add_message(
                message, metadata.get("conversation_id")
            )

            if user_message_id:
                await self.conv_service.update_message_status(
                    uuid.UUID(user_message_id), MessageStatus.COMPLETED
                )

            return message

        except Exception as e:
            if user_message_id:
                await self.conv_service.update_message_status(
                    uuid.UUID(user_message_id), MessageStatus.FAILED
                )
            raise e

    async def ask_stream(
        self,
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
                StreamPhase.RESPONSE_GENERATION, "Generating response...", progress=0.0
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

            message = Message(
                role="agent",
                parts=[TextPart(type="text", text=final_response.get("content"))],
                metadata=final_metadata,
                retrieval_context=retrieval_context,
            )

            user_message_id = _extract_message_id(conversation[-1])

            await self.conv_service.add_message(
                message, metadata.get("conversation_id")
            )
            await self.conv_service.update_message_status(
                user_message_id, MessageStatus.COMPLETED
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

    async def ask(self, request: ChatRequest) -> Tuple[Message, List[Dict]]:
        """Process a chat request and return a response."""
        with tracer.start_as_current_span("ChatService.ask") as span:
            span.set_attribute("user.id", request.message.metadata.get("user_id"))
            span.set_attribute("kb.id", request.message.metadata.get("kb_id"))
            request = self.sanitize_request(request)
            if settings.enable_websearch and request.web_search:
                web_search_config = WebSearchConfig(
                    provider=settings.websearch_provider,
                    active=True,
                    api_key=_get_api_key_for_provider(settings.websearch_provider),
                )
            else:
                web_search_config = WebSearchConfig(active=False)

            metadata = request.message.metadata
            metadata.update({"web_search_config": web_search_config.model_dump()})
            conversation = await self.sanitize_message(request.message)
            if request.agentic:
                response = await self.orchestrator_graph.run(conversation)

            else:
                response = await self.ask_normal(
                    conversation, web_search_config, metadata
                )
            return response

    async def ask_sse(
        self, request: ChatRequest
    ) -> AsyncGenerator[str | BaseMessage, None]:
        """Process a chat request and return a streaming response."""
        request = self.sanitize_request(request)
        if settings.enable_websearch and request.web_search:
            web_search_config = WebSearchConfig(
                provider=settings.websearch_provider,
                active=True,
                api_key=_get_api_key_for_provider(settings.websearch_provider),
            )
        else:
            web_search_config = WebSearchConfig(active=False)

        metadata = request.message.metadata
        conversation = await self.sanitize_message(request.message)

        if request.agentic:
            main_agent = MainAgent(kb_id=metadata.get("kb_id"))
            initial_state: AgentInputState = {
                "messages": conversation,
                "web_search": web_search_config,
            }
            response = main_agent.generate_streaming_response(initial_state)
        else:
            response = self.ask_stream(conversation, web_search_config, metadata)
        return response


def _get_api_key_for_provider(provider: SearchProvider) -> str:
    """Get API key based on the selected provider."""
    if provider == SearchProvider.TAVILY:
        return settings.tavily_api_key
    elif provider == SearchProvider.FIRECRAWL:
        return settings.firecrawl_api_key


def _extract_message_id(message: BaseMessage) -> str | None:
    """Extract message_id from LangChain message's metadata."""
    metadata = message.additional_kwargs.get("message_metadata", {})
    return metadata.get("message_id")
