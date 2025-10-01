# src/agents/graph/simple_search_graph.py
from typing import Dict, Any
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from qdrant_client.models import Filter, models
from src.agents.basic import citation_agent, response_agent, filename_agent
from src.rag.vector import vector_retrieval
from src.services.web_search_service import web_search_service
from src.utils.logger_conf import logger
from src.agents.graph.state import AgentState
import tiktoken


class SimpleSearchGraph:
    """
    Simple Search Graph - Handles straightforward queries with single retrieval.

    Flow:
    extract_filename → retrieve_documents → filter_citations → generate_response
    """

    def __init__(self, tokenizer: tiktoken.Encoding):
        self.tokenizer = tokenizer
        self.graph = self._build_graph()

    # =========================================================================
    # NODE IMPLEMENTATIONS
    # =========================================================================

    async def extract_filename_node(self, state: AgentState) -> Dict[str, Any]:
        """Extract filename from query if mentioned"""
        logger.info("Simple Search - Extracting filename")

        requested_filename = await filename_agent.extract_filename(
            query=state["original_query"]
        )

        if requested_filename:
            logger.info(f"Detected filename: {requested_filename}")

        return {"response_metadata": {"requested_filename": requested_filename}}

    async def retrieve_documents_node(
        self, state: AgentState, tool_context: Any
    ) -> Dict[str, Any]:
        """
        Retrieve documents from RAG or web search based on config
        """
        logger.info("Simple Search - Retrieving documents")

        kb_id = tool_context.state["input_message_metadata"]["kb_id"]
        web_search_config = tool_context.state.get("web_search_config", {})

        embed_top = 50
        rerank_top = 20
        max_tokens = 8192

        contextualized_query = state["contextualized_query"]
        requested_filename = state.get("response_metadata", {}).get(
            "requested_filename"
        )

        # Web search mode
        if web_search_config.get("active"):
            logger.info("Using web search")

            retrieved_docs = await web_search_service.search(
                query=contextualized_query,
                provider=web_search_config.get("provider"),
                api_key=web_search_config.get("api_key"),
                max_results=rerank_top,
            )

            search_method = "web_search"

        # RAG search mode
        else:
            logger.info("Using RAG search")

            # Build filters
            filters = Filter(must=[])
            if requested_filename:
                filters.must.append(
                    models.FieldCondition(
                        key="metadata.original_filename",
                        match=models.MatchText(text=requested_filename),
                    )
                )

            logger.info(f"Filters: {filters}")

            retrieved_docs = await vector_retrieval.retrieve(
                kb_id=str(kb_id),
                query=contextualized_query,
                filters=filters,
                top_k=embed_top,
                top_n=rerank_top,
            )

            search_method = "database_search"

        logger.info(f"Retrieved {len(retrieved_docs)} documents")

        # Token limiting
        if len(retrieved_docs) > rerank_top:
            retrieved_docs = retrieved_docs[:rerank_top]

        texts_list = [doc.page_content for doc in retrieved_docs]
        encoded_batches = self.tokenizer.encode_batch(text=texts_list, num_threads=4)
        total_tokens = sum(len(tokens) for tokens in encoded_batches)

        logger.info(f"Total tokens: {total_tokens} / {max_tokens}")

        # Truncate if needed
        if total_tokens > max_tokens:
            final_docs = []
            current_tokens = 0

            for i, doc in enumerate(retrieved_docs):
                doc_tokens = len(encoded_batches[i])
                if current_tokens + doc_tokens > max_tokens and final_docs:
                    logger.warning(
                        f"Token limit reached. Truncating from "
                        f"{len(retrieved_docs)} to {len(final_docs)} documents"
                    )
                    break
                final_docs.append(doc)
                current_tokens += doc_tokens

            retrieved_docs = final_docs

        # Add original index to metadata
        for i, doc in enumerate(retrieved_docs):
            doc.metadata["original_index"] = i

        return {
            "retrieval_contexts": [
                {
                    "original_query": state["original_query"],
                    "contextualized_query": contextualized_query,
                    "total_retrieved": len(retrieved_docs),
                    "total_cited": 0,  # Will be updated in next node
                    "cited_chunks": retrieved_docs,
                }
            ],
            "response_metadata": {
                **state.get("response_metadata", {}),
                "search_method": search_method,
                "total_retrieved": len(retrieved_docs),
            },
        }

    async def filter_citations_node(self, state: AgentState) -> Dict[str, Any]:
        """Filter relevant documents using citation agent"""
        logger.info("Simple Search - Filtering citations")

        retrieval_context = state["retrieval_contexts"][0]
        retrieved_docs = retrieval_context["cited_chunks"]

        if not retrieved_docs:
            logger.warning("No documents to filter")
            return {}

        # Extract citations
        citation_indexes = await citation_agent.extract_citations(
            history=state["conversation"],
            reference=retrieved_docs,
        )

        # Filter cited documents
        cited_docs = []
        if citation_indexes.indexes:
            cited_docs = [
                retrieved_docs[i - 1]
                for i in citation_indexes.indexes
                if 0 < i <= len(retrieved_docs)
            ]

        logger.info(f"Filtered to {len(cited_docs)} cited documents")

        # Update retrieval context
        updated_context = {
            **retrieval_context,
            "total_cited": len(cited_docs),
            "cited_chunks": cited_docs,
        }

        return {
            "retrieval_contexts": [updated_context],
            "cited_documents": cited_docs,
            "response_metadata": {
                **state.get("response_metadata", {}),
                "total_cited": len(cited_docs),
            },
        }

    async def generate_response_node(self, state: AgentState) -> Dict[str, Any]:
        """Generate final response using cited documents"""
        logger.info("Simple Search - Generating response")

        cited_docs = state["cited_documents"]

        response = await response_agent.generate_response(
            contexts=cited_docs,
            history=state["conversation"],
        )

        response_dict = response.model_dump()

        logger.info("Response generated successfully")

        return {
            "final_answer": response_dict["content"],
            "response_metadata": {
                **state.get("response_metadata", {}),
                **response_dict.get("response_metadata", {}),
            },
        }

    # =========================================================================
    # GRAPH CONSTRUCTION
    # =========================================================================

    def _build_graph(self) -> CompiledStateGraph:
        """Construct the simple search graph"""
        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("extract_filename", self.extract_filename_node)
        workflow.add_node("retrieve_documents", self.retrieve_documents_node)
        workflow.add_node("filter_citations", self.filter_citations_node)
        workflow.add_node("generate_response", self.generate_response_node)

        # Set entry point
        workflow.set_entry_point("extract_filename")

        # Linear flow
        workflow.add_edge("extract_filename", "retrieve_documents")
        workflow.add_edge("retrieve_documents", "filter_citations")
        workflow.add_edge("filter_citations", "generate_response")
        workflow.add_edge("generate_response", END)

        return workflow.compile()

    # =========================================================================
    # PUBLIC INTERFACE
    # =========================================================================

    async def run(self, state: AgentState, tool_context: Any) -> AgentState:
        """Execute simple search graph"""
        logger.info("=" * 80)
        logger.info("STARTING SIMPLE SEARCH GRAPH")
        logger.info(f"Query: {state['contextualized_query']}")
        logger.info("=" * 80)

        result = await self.graph.ainvoke(state, {"tool_context": tool_context})

        logger.info("=" * 80)
        logger.info("SIMPLE SEARCH GRAPH COMPLETED")
        logger.info(f"Cited documents: {len(result.get('cited_documents', []))}")
        logger.info("=" * 80)

        return result
