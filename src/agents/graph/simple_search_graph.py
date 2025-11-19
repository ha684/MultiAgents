# src/agents/graph/simple_search_graph.py
from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.basic import citation_agent
from src.agents.graph.base import GraphAgentBase
from src.agents.tools.server.mcp_retrieve_tools import rag_search, web_search
from src.domain.entities.graph import RunConfig
from src.domain.entities.state import SimpleSearchState
from src.utils import truncate_docs_by_tokens
from src.utils.logger_conf import logger


class SimpleSearchGraph(GraphAgentBase[SimpleSearchState]):
    """
    Simple Search Graph - Handles straightforward queries with single retrieval.

    Flow:
    extract_filename → retrieve_documents → filter_citations → generate_response
    """

    def __init__(self):
        super().__init__()
        self.graph_name = "SimpleSearchGraph"
        self.compiled_graph = self._build_graph()

    @property
    def graph(self) -> CompiledStateGraph:
        return self.compiled_graph

    def default_run_config(self) -> RunConfig:
        return RunConfig(
            graph_name=self.graph_name, recursion_limit=10, timeout_seconds=180
        )

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

        direction = state["direction"]
        context_metadata = {
            "kb_id": kb_id,
        }

        if web_search_config.get("active"):
            logger.info("Using web search")
            retrieved_docs = await web_search(
                query=direction,
            )
            search_method = "web"

        else:
            logger.info("Using RAG search")
            retrieved_docs = await rag_search(
                query=direction, context_metadata=context_metadata
            )
            search_method = "rag"

        logger.info(f"Retrieved {len(retrieved_docs)} documents")

        retrieved_docs = truncate_docs_by_tokens(
            retrieved_docs, max_tokens=8192, tokenizer=self.tokenizer
        )

        for i, doc in enumerate(retrieved_docs):
            doc.metadata["original_index"] = i

        seen_urls: set[str] = set(state.get("seen_urls", set()))
        seen_doc_ids: set[str] = set(state.get("seen_doc_ids", set()))
        dup_ratio_threshold: float = float(state.get("duplicate_skip_ratio", 0.8))

        urls = [
            (doc.metadata.get("original_filename") or "").strip()
            for doc in retrieved_docs
        ]
        doc_ids = [
            (doc.metadata.get("document_id") or "").strip() for doc in retrieved_docs
        ]

        if search_method == "web":
            keys = urls
            seen_keys = seen_urls
        else:
            keys = doc_ids
            seen_keys = seen_doc_ids

        non_empty_keys = [k for k in keys if k]
        new_keys = [k for k in non_empty_keys if k not in seen_keys]
        duplicates = len(non_empty_keys) - len(new_keys)
        total_keyed = len(non_empty_keys)
        dup_ratio = (duplicates / total_keyed) if total_keyed else 1.0

        early_terminate = (dup_ratio >= dup_ratio_threshold) or (len(new_keys) == 0)

        response_meta = {
            **state.get("response_metadata", {}),
            "search_method": search_method,
            "favicons": [doc.metadata.get("favicon", "") for doc in retrieved_docs],
            "urls": urls,
            "doc_ids": doc_ids,
            "sources_count": len(retrieved_docs),
            "total_cited": 0,
            "duplicate_ratio": dup_ratio,
            "early_terminate": early_terminate,
            "new_urls": [u for u in urls if u and u not in seen_urls],
            "new_doc_ids": [d for d in doc_ids if d and d not in seen_doc_ids],
        }

        return {
            "cited_documents": retrieved_docs,
            "response_metadata": response_meta,
            "early_terminate": early_terminate,
            "direction": direction,
        }

    async def filter_citations_node(self, state: SimpleSearchState) -> Dict[str, Any]:
        if state.get("early_terminate"):
            logger.info("Early terminate is True -> skip citation filtering")
            cited_docs = []
            meta = {
                **state.get("response_metadata", {}),
                "sources_count": 0,
                "total_cited": 0,
                "filter_skipped": True,
            }
            return {"cited_documents": cited_docs, "response_metadata": meta}

        retrieved_docs = state["cited_documents"]
        if not retrieved_docs:
            logger.warning("No documents to filter")
            return {}

        citation_indexes = await citation_agent.ainvoke(
            query=state["direction"],
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
                "sources_count": len(cited_docs),
                "total_cited": len(cited_docs),
            },
        }

    def _build_graph(self) -> CompiledStateGraph:
        """Construct the simple search graph"""
        workflow = StateGraph(SimpleSearchState)

        workflow.add_node("retrieve_documents", self.retrieve_documents_node)
        workflow.add_node("filter_citations", self.filter_citations_node)

        workflow.set_entry_point("retrieve_documents")

        workflow.add_edge("retrieve_documents", "filter_citations")

        workflow.set_finish_point("filter_citations")

        return workflow.compile(name=self.graph_name)
