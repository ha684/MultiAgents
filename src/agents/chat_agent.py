from typing import List, Dict, Any, cast, AsyncGenerator, Union, Generator, Tuple
from qdrant_client.models import Filter, models
from src.agents.citation_agent import CitationAgent
from src.agents.filename_agent import FilenameAgent
from src.rag.vector import vector_retrieval
from src.agents.response_agent import ResponseAgent
from src.agents.verification_agent import VerificationAgent
from src.agents.folder_categorization_agent import FolderCategorizationAgent
from src.agents.query_context_agent import QueryContextAgent
from langchain_core.messages import BaseMessage
from src.utils.logger_conf import logger
from src.utils.decorators import singleton
from src.common.streaming import StreamEventBuilder
from src.models.streaming import StreamPhase
import tiktoken
from src.services.web_search_service import search_service
from src.models.chat import WebSearchConfig
from src.services.conversation_service import ConversationService
from src.common.types import Message, RetrievalContext
from src.common.types import TextPart
from src.tracking.observability import tracer


@singleton
class ChatAgent:
    def __init__(self):
        self.response_agent = ResponseAgent()
        self.verification_agent = VerificationAgent()
        self.citation_agent = CitationAgent()
        self.folder_categorization_agent = FolderCategorizationAgent()
        self.filename_agent = FilenameAgent()
        self.query_context_agent = QueryContextAgent()
        self.conv_service = ConversationService()
        self.tokenizer = tiktoken.encoding_for_model("gpt-4o")
        logger.info("Chat Agent initialized successfully.")

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
                    contextualized_query = (
                        await self.query_context_agent.contextualize_query(
                            history=conversation
                        )
                    )
                span.set_attribute("contextualized_query", contextualized_query)
            if web_search_config.active:
                with tracer.start_as_current_span("search_service.search"):
                    retrieved_docs = await search_service.search(
                        query=contextualized_query,
                        provider=web_search_config.provider,
                        api_key=web_search_config.api_key,
                        max_results=rerank_top,
                    )
            else:
                with tracer.start_as_current_span("FilenameAgent.extract_filename"):
                    requested_filename = await self.filename_agent.extract_filename(
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
                    citation_indexes = await self.citation_agent.extract_citations(
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
            contextualized_query = await self.query_context_agent.contextualize_query(
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
            retrieved_docs = await search_service.search(
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
            requested_filename = await self.filename_agent.extract_filename(
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
            citation_indexes = await self.citation_agent.extract_citations(
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
        conversation: List[Message],
        web_search_config: WebSearchConfig,
        metadata: Dict[str, Any],
    ) -> Tuple[Message, List[Dict]]:
        """Handles non-streaming (full text) response."""
        retrieval_context = await self._retrieve(
            conversation, web_search_config, metadata
        )
        with tracer.start_as_current_span("ResponseAgent.generate_response"):
            response = await self.response_agent.generate_response(
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

        await self.conv_service.add_message(message, metadata.get("conversation_id"))
        return message

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

            response_generator = self.response_agent.generate_streaming_response(
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

            await self.conv_service.add_message(
                message, metadata.get("conversation_id")
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
