from typing import List, Dict, Any, cast, AsyncGenerator, Union, Generator
from qdrant_client.models import Filter, models
from src.agents.citation_agent import CitationAgent
from src.agents.filename_agent import FilenameAgent
from src.rag.vector import vector_retrieval
from src.agents.response_agent import ResponseAgent
from src.agents.verification_agent import VerificationAgent
from src.agents.folder_categorization_agent import FolderCategorizationAgent
from src.agents.query_context_agent import QueryContextAgent
from langchain_core.messages import BaseMessage
from src.models.chat import ChatRequest
from src.utils.logger_conf import logger
from langchain_core.documents import Document
from src.utils.decorators import singleton
from src.common.streaming import StreamEventBuilder
from src.models.streaming import StreamPhase
from src.utils.reference import normalize_ref
from src.models.reference import Reference
import tiktoken
from src.services.web_search_service import search_service
from src.models.chat import WebSearchConfig

@singleton
class ChatAgent:
    def __init__(self):
        self.response_agent = ResponseAgent()
        self.verification_agent = VerificationAgent()
        self.citation_agent = CitationAgent()
        self.folder_categorization_agent = FolderCategorizationAgent()
        self.filename_agent = FilenameAgent()
        self.query_context_agent = QueryContextAgent()
        self.tokenizer = tiktoken.encoding_for_model("gpt-4o")
        logger.info("Chat Agent initialized successfully.")

    async def _retrieve(
        self, request: ChatRequest, web_search_config: WebSearchConfig
    ) -> List[Document]:
        """Retrieves relevant documents based on the query and knowledge base ID."""
        embed_top = 50
        rerank_top = 20
        original_query = request.messages[-1].content
        kb_id = request.knowledge_base_id
        folder_structure = request.folder_structure or {}
        contextualized_query = original_query
        cited_docs = []
        retrieved_docs = []
        max_tokens = 8192

        logger.info(
            f"Retrieving documents for query: {original_query} in knowledgebase: {kb_id}"
        )

        logger.info(f"Folder structure: {folder_structure}")

        if len(request.messages) > 2:
            contextualized_query = await self.query_context_agent.contextualize_query(
                history=request.messages
            )
            logger.info(f"Contextualized query: {contextualized_query}")

        # relevant_folder = self.folder_categorization_agent.get_relevant_folder(
        #     query=query, folder_structure=folder_structure
        # )
        # logger.info(f"Relevant folder: {relevant_folder}")
        # NOTE: For now, we are temporarily disabling folder categorization

        relevant_folder = request.folder_context or None
        if web_search_config.active:
            retrieved_docs = await search_service.search(
                query=contextualized_query,
                provider=web_search_config.provider,
                api_key=web_search_config.api_key,
                max_results=rerank_top,
            )
        else:
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

            if relevant_folder:
                logger.info(f"Relevant folder: {relevant_folder}")
                cast(List[models.Condition], filters.must).append(
                    models.FieldCondition(
                        key="metadata.folder_path",
                        match=models.MatchAny(any=[relevant_folder]),
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

        logger.info(
            f"Retrieved {len(retrieved_docs)} documents for query: {contextualized_query} in knowledgebase: {kb_id}"
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

        # Stash the original index in the metadata before citation filtering
        for i, doc in enumerate(retrieved_docs):
            doc.metadata["original_index"] = i

        if retrieved_docs:
            citation_indexes = await self.citation_agent.extract_citations(
                history=request.messages,
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

        return cited_docs

    async def _retrieve_stream(
        self, request: ChatRequest, web_search_config: WebSearchConfig
    ) -> Generator[Union[str, List[Document]], None, None]:
        """Retrieves relevant documents based on the query and knowledge base ID."""
        embed_top = 50
        rerank_top = 20
        original_query = request.messages[-1].content
        kb_id = request.knowledge_base_id
        folder_structure = request.folder_structure or {}
        contextualized_query = original_query
        cited_docs = []
        retrieved_docs = []
        max_tokens = 8192

        logger.info(
            f"Retrieving documents for query: {original_query} in knowledgebase: {kb_id}"
        )

        logger.info(f"Folder structure: {folder_structure}")

        if len(request.messages) > 2:
            yield StreamEventBuilder.status_update(
                StreamPhase.CONTEXT_ANALYSIS,
                "Analyzing conversation context...",
                progress=0.1,
            )
            contextualized_query = await self.query_context_agent.contextualize_query(
                history=request.messages
            )
            logger.info(f"Contextualized query: {contextualized_query}")

        # relevant_folder = self.folder_categorization_agent.get_relevant_folder(
        #     query=query, folder_structure=folder_structure
        # )
        # logger.info(f"Relevant folder: {relevant_folder}")
        # NOTE: For now, we are temporarily disabling folder categorization

        relevant_folder = request.folder_context or None
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

            if relevant_folder:
                logger.info(f"Relevant folder: {relevant_folder}")
                cast(List[models.Condition], filters.must).append(
                    models.FieldCondition(
                        key="metadata.folder_path",
                        match=models.MatchAny(any=[relevant_folder]),
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
                history=request.messages,
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

        yield cited_docs

    async def ask_normal(
        self, request: ChatRequest, web_search_config: WebSearchConfig
    ) -> Dict[str, Any]:
        """Handles non-streaming (full text) response."""
        citations = await self._retrieve(request, web_search_config)
        response = await self.response_agent.generate_response(
            contexts=citations,
            history=request.messages,
        )
        response_dict = response.model_dump()
        if citations:
            response_dict["reference"] = create_reference(citations)
        if web_search_config.active:
            response_dict["search_method"] = "web_search"
        else:
            response_dict["search_method"] = "database_search"
        return response_dict

    async def ask_stream(
        self, request: ChatRequest, web_search_config: WebSearchConfig
    ) -> AsyncGenerator[str | BaseMessage, None]:
        """Handles streaming response with robust error handling."""
        try:
            yield StreamEventBuilder.message_start()

            retrieve_generator = self._retrieve_stream(request, web_search_config)
            citations = []

            async for event in retrieve_generator:
                if isinstance(event, list):
                    citations = event
                else:
                    yield event

            yield StreamEventBuilder.status_update(
                StreamPhase.RESPONSE_GENERATION, "Generating response...", progress=0.0
            )

            response_generator = self.response_agent.generate_streaming_response(
                contexts=citations,
                history=request.messages,
            )

            i = 0
            async for chunk in response_generator:
                if isinstance(chunk, str) and chunk != "error":
                    yield StreamEventBuilder.content_delta(chunk, index=i)
                    i += 1
                elif isinstance(chunk, dict):
                    break
                else:
                    yield StreamEventBuilder.error(
                        "LLM issue", "Error while streaming response", code=500
                    )

            yield StreamEventBuilder.status_update(
                StreamPhase.COMPLETE, "Response generation complete", progress=1.0
            )
            references = create_reference(citations) if citations else None

            if web_search_config.active:
                metadata = {"search_method": "web_search"}
            else:
                metadata = {"search_method": "database_search"}

            yield StreamEventBuilder.message_stop(
                references=references,
                metadata=metadata,
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


def create_reference(retrieved_docs: List[Document]) -> List[Dict]:
    """Create reference objects from retrieved documents."""
    references = []
    formated_docs = normalize_ref(retrieved_docs)

    for i, doc in enumerate(formated_docs):
        reference = Reference(
            source_id=str(doc.metadata.get("_id")),
            source_index=doc.metadata.get("original_index", i),
            source=str(doc.metadata.get("original_filename")),
            quote="",
            page_content=doc.page_content,
        )
        references.append(reference.model_dump())

    return references
