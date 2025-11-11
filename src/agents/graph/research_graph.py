# src/agents/graph/research_graph.py
from __future__ import annotations

from typing import Any, Dict
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import tiktoken
from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.basic import (
    citation_agent,
    compress_agent,
    verification_agent,
    reflection_agent,
)
from src.agents.graph.base import GraphAgentBase
from src.agents.tools.server.mcp_retrieve_tools import rag_search, web_search
from src.domain.entities.graph import RunConfig
from src.domain.entities.state import ResearchState
from src.utils import truncate_docs_by_tokens
from src.utils.logger_conf import logger


def _normalize_url(meta: Dict[str, Any]) -> str:
    """Normalize URL by removing tracking params and fragments."""
    url = (
        meta.get("url")
        or meta.get("source")
        or meta.get("resolved_url")
        or meta.get("original_filename")
        or ""
    )
    try:
        p = urlparse(url)
        if not p.scheme or not p.netloc:
            return url
        q = [
            (k, v)
            for k, v in parse_qsl(p.query, keep_blank_values=True)
            if not k.lower().startswith("utm_")
        ]
        new_query = urlencode(q, doseq=True)
        return urlunparse(
            (p.scheme.lower(), p.netloc.lower(), p.path, "", new_query, "")
        )
    except Exception:
        return url


class ResearchGraph(GraphAgentBase[ResearchState]):
    """
    Adaptive Research Graph - Agentic research with dynamic evaluation like ChatGPT.

    Flow:
    1. Initialize → Generate Direction → Execute Searches → Extract Learnings
    2. Evaluate Sufficiency: Agent decides if research is adequate or needs more
    3. If insufficient, generate next direction and repeat; if sufficient, finalize
    4. Safety limit: max_iterations to prevent infinite loops
    """

    def __init__(self):
        super().__init__()
        self.graph_name = "ResearchGraph"
        self.compiled_graph = self._build_graph()
        self.tokenizer = tiktoken.encoding_for_model("gpt-4o")
        self.default_breadth = 2
        self.max_iterations = 10
        self.min_knowledge_threshold = 500
        logger.info("ResearchGraph initialized (adaptive agent mode).")

    @property
    def graph(self) -> CompiledStateGraph:
        return self.compiled_graph

    def default_run_config(self) -> RunConfig:
        return RunConfig(
            graph_name=self.graph_name, recursion_limit=10, timeout_seconds=300
        )

    async def initialize_node(self, state: ResearchState) -> ResearchState:
        """Initialize research parameters and check source availability."""
        breadth = state.get("breadth", self.default_breadth)

        rag_available = True
        web_available = True

        try:
            test_docs = await rag_search(
                query=state["contextualized_query"],
                context_metadata=state["context_metadata"],
            )
            if not test_docs:
                rag_available = False
        except Exception as e:
            logger.warning(f"RAG unavailable: {e}")
            rag_available = False

        return {
            "breadth": breadth,
            "current_depth_level": 0,
            "current_direction": state["contextualized_query"],
            "thinking_notes": f"Starting research on: {state['contextualized_query']}",
            "accumulated_knowledge": "",
            "learnings": [],
            "search_count": 0,
            "search_history": [],
            "citation_counter": 0,
            "cited_documents": state.get("cited_documents", []),
            "citation_map": state.get("citation_map", []),
            "used_rag_ids": [],
            "used_web_urls": [],
            "rag_available": rag_available,
            "web_available": web_available,
        }

    async def generate_direction_node(self, state: ResearchState) -> Dict[str, Any]:
        """
        Generate focused research direction for current depth level.
        Similar to ChatGPT's progressive thinking.
        """
        depth_level = state.get("current_depth_level", 0)
        query = state["contextualized_query"]

        if depth_level == 0:
            direction = query
            thinking = f"Investigating: {query}"
        else:
            try:
                resp, thinking_content = await reflection_agent.ainvoke(state=state)
                direction = resp if resp else query
                thinking = (
                    thinking_content
                    if thinking_content
                    else f"Exploring next aspect of: {query}"
                )
            except Exception as e:
                logger.error(f"Failed to generate direction: {e}")
                direction = query
                thinking = f"Continuing research on: {query}"

        logger.info(f"[Depth {depth_level}] {thinking}")
        logger.info(f"[Direction] {direction}")

        return {
            "current_direction": direction,
            "thinking_notes": thinking,
        }

    async def execute_searches_node(self, state: ResearchState) -> Dict[str, Any]:
        """
        Execute focused searches based on current direction.
        Performs 'breadth' number of searches with smart source selection.
        """
        direction = state["current_direction"]
        breadth = state.get("breadth", self.default_breadth)
        context_metadata = state["context_metadata"]

        rag_available = state.get("rag_available", True)
        web_available = state.get("web_available", True)

        if not rag_available and not web_available:
            logger.error("Both RAG and Web unavailable!")
            return {}

        searches_to_perform = []

        if rag_available and web_available:
            for i in range(breadth):
                searches_to_perform.append("rag" if i % 2 == 0 else "web")
        elif rag_available:
            searches_to_perform.append("rag")
        elif web_available:
            searches_to_perform.append("web")

        all_documents = []
        search_history = list(state.get("search_history", []))
        search_count = state.get("search_count", 0)

        for search_type in searches_to_perform:
            try:
                if search_type == "rag":
                    docs = await rag_search(
                        query=direction, context_metadata=context_metadata
                    )
                else:
                    docs = await web_search(query=direction)

                if docs:
                    all_documents.extend(docs)
                    search_history.append(
                        {
                            "search_type": search_type,
                            "query": direction,
                            "doc_count": len(docs),
                            "depth_level": state.get("current_depth_level", 0),
                        }
                    )
                    logger.info(
                        f"[Search] {search_type.upper()}: {len(docs)} documents for '{direction}'"
                    )
                else:
                    logger.warning(
                        f"[Search] {search_type.upper()}: No results for '{direction}'"
                    )

            except Exception as e:
                logger.error(f"[Search] {search_type.upper()} failed: {e}")
                continue

        if not all_documents:
            logger.warning("No documents retrieved from any source!")
            return {
                "search_count": search_count + len(searches_to_perform),
                "search_history": search_history,
            }

        used_rag_ids = set(state.get("used_rag_ids", []))
        used_web_urls = set(state.get("used_web_urls", []))

        new_docs = []
        for doc in all_documents:
            meta = doc.metadata
            doc_id = meta.get("document_id")
            url = _normalize_url(meta)

            if doc_id and doc_id in used_rag_ids:
                continue
            if url and url in used_web_urls:
                continue

            new_docs.append(doc)
            if doc_id:
                used_rag_ids.add(doc_id)
            if url:
                used_web_urls.add(url)

        if not new_docs:
            logger.warning("All documents were duplicates!")
            new_docs = all_documents[:breadth]

        logger.info(f"After dedup: {len(new_docs)}/{len(all_documents)} documents")
        new_docs = truncate_docs_by_tokens(
            new_docs, max_tokens=8192, tokenizer=self.tokenizer
        )

        try:
            relevant_indices = await citation_agent.ainvoke(
                history=[HumanMessage(content=direction)], reference=new_docs
            )
            if relevant_indices and getattr(relevant_indices, "indexes", None):
                idxs = [i for i in relevant_indices.indexes if 0 < i <= len(new_docs)]
                if idxs:
                    new_docs = [new_docs[i - 1] for i in idxs]
                    logger.info(f"Filtered to {len(new_docs)} relevant documents")
        except Exception as e:
            logger.warning(f"Citation filtering failed: {e}, using all docs")

        return {
            "search_count": search_count + len(searches_to_perform),
            "search_history": search_history,
            "used_rag_ids": list(used_rag_ids),
            "used_web_urls": list(used_web_urls),
            "_temp_documents": new_docs,
        }

    async def extract_learnings_node(self, state: ResearchState) -> Dict[str, Any]:
        """
        Process search results to extract learnings.
        Add citations and compress into accumulated knowledge.
        """
        docs = state.get("_temp_documents", [])
        if not docs:
            logger.warning("No documents to process")
            return {}

        direction = state["current_direction"]

        citation_start = state.get("citation_counter", 0)
        cited_documents = list(state.get("cited_documents", []))
        citation_map = list(state.get("citation_map", []))

        docs_with_citations = []
        current_citation = citation_start

        for doc in docs:
            doc_copy = doc.model_copy(deep=True) if hasattr(doc, "model_copy") else doc
            content = doc_copy.page_content
            doc_copy.page_content = f"[CITATION: {current_citation}] {content}"

            docs_with_citations.append(doc_copy)
            cited_documents.append(doc)
            citation_map.append(
                {
                    "index": current_citation,
                    "metadata": doc.metadata,
                }
            )
            current_citation += 1

        try:
            compressed = await compress_agent.ainvoke(
                query=direction, reference=docs_with_citations
            )
        except Exception as e:
            logger.error(f"Compression failed: {e}")
            compressed = "\n\n".join([d.page_content for d in docs_with_citations[:3]])

        learning_point = f"[Depth {state.get('current_depth_level', 0)}] {state.get('thinking_notes', '')}: {compressed[:200]}..."

        existing = state.get("accumulated_knowledge", "")
        if existing:
            accumulated = f"{existing}\n\n## {direction}\n\n{compressed}"
        else:
            accumulated = f"## {direction}\n\n{compressed}"

        learnings = list(state.get("learnings", []))
        learnings.append(learning_point)

        logger.info(f"[Learnings] Extracted learning from {len(docs)} documents")

        return {
            "accumulated_knowledge": accumulated,
            "learnings": learnings,
            "citation_counter": current_citation,
            "cited_documents": cited_documents,
            "citation_map": citation_map,
        }

    async def evaluate_sufficiency_node(self, state: ResearchState) -> Dict[str, Any]:
        """
        Evaluate if current research is sufficient or if we need to continue.
        This makes it agentic - it decides based on quality, not a counter.
        """
        knowledge = state.get("accumulated_knowledge", "")
        iteration = state.get("current_depth_level", 0)
        learnings = state.get("learnings", [])

        if iteration >= self.max_iterations:
            logger.warning(
                f"[Evaluate] Max iterations ({self.max_iterations}) reached. Stopping."
            )
            return {"_should_continue": False}

        if not knowledge or len(knowledge) < self.min_knowledge_threshold:
            logger.info(
                "[Evaluate] Insufficient knowledge accumulated. Continue research."
            )
            return {"_should_continue": True}

        try:
            resp = await verification_agent.ainvoke(state=state)
            is_sufficient = resp.get("is_sufficient", False)
            missing = resp.get("missing_aspects", [])

            if missing:
                top_missing = missing[:3]
                logger.info(f"[Evaluate] Missing: {', '.join(missing[:3])}")
                gaps_line = "; ".join(top_missing)
                learnings.append(
                    f"[Depth {iteration}] Verification gaps, here what are the missing parts that we need to fill: {gaps_line}"
                )

            logger.info(f"[Evaluate] Sufficient: {is_sufficient}")

            return {
                "learnings": learnings,
                "_should_continue": not is_sufficient,
                "_evaluation_result": {
                    "is_sufficient": is_sufficient,
                    "missing_aspects": missing,
                },
            }

        except Exception as e:
            logger.error(
                f"[Evaluate] Evaluation failed: {e}. Defaulting to continue once more."
            )
            return {"_should_continue": iteration < 2}

    def decide_continue_or_stop(self, state: ResearchState) -> str:
        """Route based on evaluation result."""
        should_continue = state.get("_should_continue", False)

        if should_continue:
            logger.info("[Router] Research insufficient. Continuing...")
            return "continue"
        else:
            logger.info("[Router] Research sufficient. Finalizing...")
            return "finalize"

    async def continue_iteration_node(self, state: ResearchState) -> Dict[str, Any]:
        """Prepare for next research iteration."""
        return {
            "current_depth_level": state.get("current_depth_level", 0) + 1,
        }

    async def finalize_node(self, state: ResearchState) -> Dict[str, Any]:
        """Final preparation of research results."""
        evaluation = state.get("_evaluation_result", {})

        logger.info("=" * 70)
        logger.info("[Finalize] Research Complete")
        logger.info("=" * 70)
        logger.info(f"Iterations: {state.get('current_depth_level', 0)}")
        logger.info(f"Total searches: {state.get('search_count', 0)}")
        logger.info(f"Total citations: {state.get('citation_counter', 0)}")
        logger.info(
            f"Knowledge length: {len(state.get('accumulated_knowledge', ''))} chars"
        )

        if evaluation:
            logger.info(f"Sufficiency: {evaluation.get('is_sufficient', 'N/A')}")
            logger.info(f"Confidence: {evaluation.get('confidence', 0):.2f}")
            logger.info(f"Reasoning: {evaluation.get('reasoning', 'N/A')}")

        logger.info("=" * 70)

        return {}

    def _build_graph(self) -> CompiledStateGraph:
        """Build the adaptive research graph with agent evaluation."""
        workflow = StateGraph(ResearchState)

        workflow.add_node("initialize", self.initialize_node)
        workflow.add_node("generate_direction", self.generate_direction_node)
        workflow.add_node("execute_searches", self.execute_searches_node)
        workflow.add_node("extract_learnings", self.extract_learnings_node)
        workflow.add_node("evaluate_sufficiency", self.evaluate_sufficiency_node)
        workflow.add_node("continue_iteration", self.continue_iteration_node)
        workflow.add_node("finalize", self.finalize_node)

        workflow.set_entry_point("initialize")

        workflow.add_edge("initialize", "generate_direction")
        workflow.add_edge("generate_direction", "execute_searches")
        workflow.add_edge("execute_searches", "extract_learnings")

        workflow.add_edge("extract_learnings", "evaluate_sufficiency")

        workflow.add_conditional_edges(
            "evaluate_sufficiency",
            self.decide_continue_or_stop,
            {
                "continue": "continue_iteration",
                "finalize": "finalize",
            },
        )

        workflow.add_edge("continue_iteration", "generate_direction")

        workflow.add_edge("finalize", END)

        return workflow.compile(name=self.graph_name)
