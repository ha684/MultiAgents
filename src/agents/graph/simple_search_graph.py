# src/agents/graph/simple_search_graph.py
from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph
import tiktoken

from src.agents.basic import citation_agent, filename_agent
from src.utils.logger_conf import logger
from src.agents.graph.state import SimpleSearchState
from src.agents.tools.server.mcp_retrieve_tools import rag_search, web_search
from src.agents.graph.base import GraphAgentBase, RunConfig


class SimpleSearchGraph(GraphAgentBase[SimpleSearchState]):
    """
    Simple Search Graph - Handles straightforward queries with single retrieval.

    Flow:
    extract_filename → retrieve_documents → filter_citations → generate_response
    """

    def __init__(self, tokenizer: tiktoken.Encoding):
        self.tokenizer = tokenizer
        self.graph_name = "SimpleSearchGraph"
        self.compiled_graph = self._build_graph()

    @property
    def graph(self) -> CompiledStateGraph:
        return self.compiled_graph

    def default_run_config(self) -> RunConfig:
        return RunConfig(
            graph_name=self.graph_name, recursion_limit=10, timeout_seconds=180
        )

    async def extract_filename_node(self, state: SimpleSearchState) -> Dict[str, Any]:
        """Extract filename from query if mentioned"""
        requested_filename = await filename_agent.ainvoke(
            query=state["contextualized_query"]
        )
        if requested_filename:
            logger.info(f"Detected filename: {requested_filename}")

        return {"response_metadata": {"requested_filename": requested_filename}}

    async def retrieve_documents_node(self, state: SimpleSearchState) -> Dict[str, Any]:
        """
        Retrieve documents from RAG or web search based on config
        """
        conversation: List[BaseMessage] = state["conversation"]
        last_human_message = conversation[-1]
        kb_id = last_human_message.additional_kwargs["message_metadata"]["kb_id"]
        web_search_config: Dict[str, str] = last_human_message.additional_kwargs[
            "message_metadata"
        ]["web_search_config"]

        rerank_top = 10
        max_tokens = 8192

        contextualized_query = state["contextualized_query"]
        context_metadata = {
            "kb_id": kb_id,
        }

        if web_search_config.get("active"):
            logger.info("Using web search")
            retrieved_docs = await web_search(
                query=contextualized_query,
            )
            search_method = "web"

        else:
            logger.info("Using RAG search")
            retrieved_docs = await rag_search(
                query=contextualized_query, context_metadata=context_metadata
            )
            search_method = "rag"

        logger.info(f"Retrieved {len(retrieved_docs)} documents")

        if len(retrieved_docs) > rerank_top:
            retrieved_docs = retrieved_docs[:rerank_top]

        texts_list = [doc.page_content for doc in retrieved_docs]
        encoded_batches = self.tokenizer.encode_batch(text=texts_list, num_threads=4)
        total_tokens = sum(len(tokens) for tokens in encoded_batches)

        logger.info(f"Total tokens: {total_tokens} / {max_tokens}")

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

        for i, doc in enumerate(retrieved_docs):
            doc.metadata["original_index"] = i

        return {
            "cited_documents": retrieved_docs,
            "response_metadata": {
                **state.get("response_metadata", {}),
                "search_method": search_method,
                "favicons": [doc.metadata.get("favicon", "") for doc in retrieved_docs],
                "urls": [
                    doc.metadata.get("original_filename", "") for doc in retrieved_docs
                ],
                "sources_count": len(retrieved_docs),
                "total_cited": 0,
            },
        }

    async def filter_citations_node(self, state: SimpleSearchState) -> Dict[str, Any]:
        """Filter relevant documents using citation agent"""
        logger.info("Simple Search - Filtering citations")

        retrieved_docs = state["cited_documents"]

        if not retrieved_docs:
            logger.warning("No documents to filter")
            return {}

        citation_indexes = await citation_agent.ainvoke(
            history=state["conversation"],
            reference=retrieved_docs,
        )

        cited_docs = []
        if citation_indexes.indexes:
            cited_docs = [
                retrieved_docs[i - 1]
                for i in citation_indexes.indexes
                if 0 < i <= len(retrieved_docs)
            ]

        logger.info(f"Filtered to {len(cited_docs)} cited documents")

        return {
            "cited_documents": cited_docs,
            "response_metadata": {
                **state.get("response_metadata", {}),
                "search_method": state.get("search_method", "rag"),
                "favicons": [doc.metadata.get("favicon", "") for doc in cited_docs],
                "urls": [
                    doc.metadata.get("original_filename", "") for doc in cited_docs
                ],
                "sources_count": len(cited_docs),
                "total_cited": len(cited_docs),
            },
        }

    def _build_graph(self) -> CompiledStateGraph:
        """Construct the simple search graph"""
        workflow = StateGraph(SimpleSearchState)

        workflow.add_node("extract_filename", self.extract_filename_node)
        workflow.add_node("retrieve_documents", self.retrieve_documents_node)
        workflow.add_node("filter_citations", self.filter_citations_node)

        workflow.set_entry_point("extract_filename")

        workflow.add_edge("extract_filename", "retrieve_documents")
        workflow.add_edge("retrieve_documents", "filter_citations")

        workflow.set_finish_point("filter_citations")

        return workflow.compile(name=self.graph_name)
