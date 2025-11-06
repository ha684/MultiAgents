# src/agents/graph/research_graph.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
import tiktoken

from src.agents.basic import (
    citation_agent,
    compress_agent,
    dynamic_query_agent,
    planner_agent,
    reflection_agent,
    verification_agent,
)
from src.agents.graph.base import GraphAgentBase
from src.agents.tools.server.mcp_retrieve_tools import rag_search, web_search
from src.domain.entities.graph import RunConfig
from src.domain.entities.state import ResearchState
from src.utils.logger_conf import logger


def _base_state_fragment(state: ResearchState) -> Dict[str, Any]:
    """Small helper to avoid repeating common returns."""
    return {
        "cited_documents": state.get("cited_documents", []),
        "accumulated_knowledge": state.get("accumulated_knowledge", ""),
    }


def _normalize_url_from_meta(meta: Dict[str, Any]) -> str:
    """
    Try to extract a stable URL-ish identifier for web docs and normalize it:
    - prefer 'url' -> 'source' -> 'resolved_url' -> 'original_filename'
    - strip utm_* params and fragments
    """
    cand = (
        meta.get("url")
        or meta.get("source")
        or meta.get("resolved_url")
        or meta.get("original_filename")
        or ""
    )
    try:
        p = urlparse(cand)
        if not p.scheme or not p.netloc:
            # not a real URL, return as-is (could be a filename)
            return cand
        # strip tracking params
        q = [
            (k, v)
            for k, v in parse_qsl(p.query, keep_blank_values=True)
            if not k.lower().startswith("utm_")
        ]
        new_query = urlencode(q, doseq=True)
        return urlunparse(
            (p.scheme.lower(), p.netloc.lower(), p.path, "", new_query, "")
        )  # drop fragment
    except Exception:
        return cand


def _as_dict_query(q: Any) -> Dict[str, Any]:
    """Coerce SearchQuery-like object to dict with minimal required keys."""
    if isinstance(q, dict):
        return q
    # best-effort attribute access
    out = {
        "query": getattr(q, "query", None),
        "search_type": getattr(q, "search_type", None),
        "priority": getattr(q, "priority", 0),
    }
    # filter None keys
    return {k: v for k, v in out.items() if v is not None}


def _ensure_search_type(
    st: Optional[str], rag_unavailable: bool, web_unavailable: bool
) -> Optional[str]:
    """Validate/repair search_type; return None if nothing is usable."""
    st = (st or "").lower()
    if st not in {"rag", "web"}:
        # choose a workable default
        if not web_unavailable:
            return "web"
        if not rag_unavailable:
            return "rag"
        return None
    # repair if selected type is unavailable
    if st == "web" and web_unavailable:
        return None if rag_unavailable else "rag"
    if st == "rag" and rag_unavailable:
        return None if web_unavailable else "web"
    return st


def distribute_documents_by_tokens(
    documents: list, encoded_batches: list, max_tokens: int, min_chunk_tokens: int = 100
) -> list:
    """
    Distribute token budget proportionally across all documents.

    Args:
        documents: List of documents to distribute
        encoded_batches: List of token lists for each document
        max_tokens: Maximum total tokens allowed
        min_chunk_tokens: Minimum tokens to include from a document (skip if can't meet this)

    Returns:
        List of truncated documents
    """
    if not documents:
        return []

    total_tokens = sum(len(tokens) for tokens in encoded_batches)

    # If under budget, return all documents as-is
    if total_tokens <= max_tokens:
        return documents

    # Calculate proportion of tokens each document should get
    doc_token_counts = [len(tokens) for tokens in encoded_batches]

    # Allocate tokens proportionally
    allocated_tokens = []
    for doc_tokens in doc_token_counts:
        proportion = doc_tokens / total_tokens
        allocated = int(max_tokens * proportion)
        # Ensure minimum viable chunk or skip
        allocated_tokens.append(
            max(allocated, min_chunk_tokens) if allocated >= min_chunk_tokens else 0
        )

    # If we over-allocated due to minimums, scale down proportionally
    total_allocated = sum(allocated_tokens)
    if total_allocated > max_tokens:
        scale_factor = max_tokens / total_allocated
        allocated_tokens = [int(t * scale_factor) for t in allocated_tokens]

    # Create truncated documents
    final_docs = []
    for i, doc in enumerate(documents):
        if allocated_tokens[i] == 0:
            continue

        tokens_for_doc = allocated_tokens[i]
        actual_tokens = len(encoded_batches[i])

        if actual_tokens <= tokens_for_doc:
            # Keep entire document
            final_docs.append(doc)
        else:
            # Truncate document content proportionally
            truncate_ratio = tokens_for_doc / actual_tokens
            original_content = doc.page_content
            truncate_pos = int(len(original_content) * truncate_ratio)

            # Create truncated document
            truncated_doc = type(doc)(
                page_content=original_content[:truncate_pos] + "...",
                metadata=doc.metadata,
            )
            final_docs.append(truncated_doc)

    logger.info(
        f"Token distribution: {total_tokens} -> {sum(allocated_tokens)} tokens "
        f"across {len(final_docs)}/{len(documents)} documents"
    )

    return final_docs


class ResearchGraph(GraphAgentBase[ResearchState]):
    """Research Subgraph - Deep research with iterative search loop (refactored)."""

    def __init__(self):
        super().__init__()
        self.graph_name = "ResearchGraph"
        self.compiled_graph = self._build_graph()
        self.max_searches = 20
        self.max_consecutive_failures = 3
        self.tokenizer = tiktoken.encoding_for_model("gpt-4o")
        logger.info("ResearchGraph initialized successfully (refactored).")

    @property
    def graph(self) -> CompiledStateGraph:
        return self.compiled_graph

    def default_run_config(self) -> RunConfig:
        return RunConfig(
            graph_name=self.graph_name, recursion_limit=50, timeout_seconds=600
        )

    async def query_planner_node(self, state: ResearchState) -> ResearchState:
        """Create research plan"""
        planner_response = await planner_agent.ainvoke(state)

        if not planner_response or not planner_response.get("queries"):
            logger.error("[QueryPlanner] Failed to generate plan or plan is empty.")
            return {
                "pending_queries": [],
                "completed_queries": [],
                "max_searches": self.max_searches,
                "iteration_count": 0,
                "all_search_history": [],
                "used_rag_ids": [],
                "used_web_urls": [],
                "has_tried_rag": False,
                "has_tried_web": False,
                "consecutive_search_failures": 0,
                "citation_counter": 0,
                "cited_documents": state.get("cited_documents", []),
                "rag_is_unavailable": False,
                "web_is_unavailable": False,
                "is_rag_source_relevant": True,
                "should_retry_query": False,
                "hard_stop": False,
                "citation_map": state.get("citation_map", []),
                "accumulated_knowledge": state.get("accumulated_knowledge", ""),
            }

        raw_queries = planner_response.get("queries", [])
        all_queries: List[Dict[str, Any]] = [_as_dict_query(q) for q in raw_queries]
        # sort by priority desc
        all_queries.sort(key=lambda x: x.get("priority", 0), reverse=True)

        return {
            "pending_queries": all_queries,
            "completed_queries": [],
            "max_searches": self.max_searches,
            "iteration_count": 0,
            "all_search_history": [],
            "used_rag_ids": [],
            "used_web_urls": [],
            "has_tried_rag": False,
            "has_tried_web": False,
            "consecutive_search_failures": 0,
            "citation_counter": 0,
            "cited_documents": state.get("cited_documents", []),
            "rag_is_unavailable": False,
            "web_is_unavailable": False,
            "is_rag_source_relevant": True,
            "should_retry_query": False,
            "hard_stop": False,
            "citation_map": state.get("citation_map", []),
            "accumulated_knowledge": state.get("accumulated_knowledge", ""),
        }

    def decide_after_planner(self, state: ResearchState) -> str:
        """Decides where to go after the query planner."""
        if state.get("pending_queries"):
            logger.info("[Router] Plan generated. Proceeding to pre_flight_rag_check.")
            return "pre_flight_rag_check"
        else:
            logger.warning("[Router] No plan generated. Proceeding to handle_no_plan.")
            return "handle_no_plan"

    async def pre_flight_rag_check_node(self, state: ResearchState) -> Dict[str, Any]:
        """
        Performs a single RAG check with the main query to determine if the
        entire RAG source is relevant for this session using the citation agent.
        """
        original_query = state["contextualized_query"]
        context_metadata = state["context_metadata"]

        have_rag_search_type = any(
            (pq.get("search_type") == "rag") for pq in state["pending_queries"]
        )
        if not have_rag_search_type:
            return {"is_rag_source_relevant": True, **_base_state_fragment(state)}

        try:
            documents = await rag_search(
                query=original_query, context_metadata=context_metadata
            )

            if not documents:
                logger.warning(
                    "[PreFlightCheck] RAG returned no docs. Mark irrelevant."
                )
                return {
                    "is_rag_source_relevant": False,
                    "rag_is_unavailable": True,
                    **_base_state_fragment(state),
                }

            relevant_indices = await citation_agent.ainvoke(
                history=[HumanMessage(content=original_query)], reference=documents
            )

            if not relevant_indices or not getattr(relevant_indices, "indexes", None):
                logger.warning(
                    "[PreFlightCheck] Citation agent found no relevant RAG docs. Mark RAG irrelevant."
                )
                return {
                    "is_rag_source_relevant": False,
                    "rag_is_unavailable": True,
                    **_base_state_fragment(state),
                }

        except Exception as e:
            logger.error(f"[PreFlightCheck] RAG pre-flight failed: {e}. Disabling RAG.")
            return {
                "is_rag_source_relevant": False,
                "rag_is_unavailable": True,
                **_base_state_fragment(state),
            }

        return {"is_rag_source_relevant": True, **_base_state_fragment(state)}

    async def handle_no_plan_node(self, state: ResearchState) -> Dict[str, Any]:
        """Go directly to dynamic query generator if planner fails."""
        verification_result = {
            "is_sufficient": False,
            "missing_aspects": [state["contextualized_query"]],
        }
        return {
            "verification_result": verification_result,
            **_base_state_fragment(state),
        }

    async def search_executor_node(self, state: ResearchState) -> Dict[str, Any]:
        """Execute search query with robust failure handling. Always bumps iteration when consuming a query."""
        if not state.get("pending_queries"):
            logger.warning("[SearchExecutor] No pending queries. Skipping execution.")
            return {**_base_state_fragment(state)}

        current_query = dict(state["pending_queries"][0])  # do not mutate original
        remaining_queries = list(state["pending_queries"][1:])

        requested_type = current_query.get("search_type")
        query_text = current_query.get("query")
        context_metadata = state["context_metadata"]

        rag_unavailable = bool(state.get("rag_is_unavailable", False))
        web_unavailable = bool(state.get("web_is_unavailable", False))
        is_rag_relevant = bool(state.get("is_rag_source_relevant", True))

        # Repair/validate search_type
        search_type = _ensure_search_type(
            requested_type, rag_unavailable, web_unavailable
        )

        # If RAG requested but deemed irrelevant, try switch to web
        if search_type == "rag" and not is_rag_relevant:
            logger.warning(
                f"[SearchExecutor] RAG deemed irrelevant. Switching query '{query_text}' to Web if possible."
            )
            if not web_unavailable:
                search_type = "web"
                current_query["search_type"] = "web"
            else:
                # both paths unusable -> consume this query and trigger hard stop
                logger.error(
                    "[SearchExecutor] RAG irrelevant and Web unavailable. Hard stop."
                )
                return {
                    "completed_queries": state.get("completed_queries", [])
                    + [current_query],
                    "pending_queries": remaining_queries,
                    "iteration_count": state.get("iteration_count", 0) + 1,
                    "consecutive_search_failures": state.get(
                        "consecutive_search_failures", 0
                    )
                    + 1,
                    "hard_stop": True,
                    **_base_state_fragment(state),
                }

        # If after repair still nothing usable -> both unavailable
        if search_type is None:
            logger.error(
                "[SearchExecutor] Both Web and RAG are unavailable. Hard stop."
            )
            return {
                "completed_queries": state.get("completed_queries", [])
                + [current_query],
                "pending_queries": remaining_queries,
                "iteration_count": state.get("iteration_count", 0) + 1,
                "consecutive_search_failures": self.max_consecutive_failures,
                "hard_stop": True,
                **_base_state_fragment(state),
            }

        documents = []
        consecutive_search_failures = state.get("consecutive_search_failures", 0)

        try:
            if search_type == "rag":
                documents = await rag_search(
                    query=query_text, context_metadata=context_metadata
                )
            else:  # web
                documents = await web_search(query=query_text)

            max_tokens = 8192
            texts_list = [doc.page_content for doc in documents]
            encoded_batches = self.tokenizer.encode_batch(
                text=texts_list, num_threads=4
            )
            total_tokens = sum(len(tokens) for tokens in encoded_batches)

            logger.info(f"Total tokens: {total_tokens} / {max_tokens}")

            if total_tokens > max_tokens:
                documents = distribute_documents_by_tokens(
                    documents=documents,
                    encoded_batches=encoded_batches,
                    max_tokens=max_tokens,
                    min_chunk_tokens=100,
                )
            consecutive_search_failures = 0
        except Exception as e:
            logger.error(
                f"[SearchExecutor] HARD FAILURE in {search_type.upper()} search for '{query_text}'. Error: {e}"
            )
            new_rag_unavail = rag_unavailable
            new_web_unavail = web_unavailable
            fallback_type = ""

            if search_type == "rag":
                new_rag_unavail = True
                if not web_unavailable:
                    fallback_type = "web"
            else:
                new_web_unavail = True
                if not rag_unavailable:
                    fallback_type = "rag"

            new_pending_queries = list(remaining_queries)
            if fallback_type:
                logger.warning(
                    f"[SearchExecutor] Switching all future '{search_type}' queries to '{fallback_type}'."
                )
                for i in range(len(new_pending_queries)):
                    if new_pending_queries[i].get("search_type") == search_type:
                        new_pending_queries[i]["search_type"] = fallback_type

            hard_stop = new_rag_unavail and new_web_unavail

            return {
                "completed_queries": state.get("completed_queries", [])
                + [current_query],
                "pending_queries": new_pending_queries,
                "iteration_count": state.get("iteration_count", 0) + 1,
                "consecutive_search_failures": consecutive_search_failures + 1,
                "rag_is_unavailable": new_rag_unavail,
                "web_is_unavailable": new_web_unavail,
                "hard_stop": hard_stop,
                **_base_state_fragment(state),
            }

        search_result: Dict[str, Any] = {
            "query": query_text,
            "documents": documents,
            "search_type": search_type,
            "processed": False,
        }

        return {
            "search_results": search_result,
            "completed_queries": state.get("completed_queries", []) + [current_query],
            "pending_queries": remaining_queries,
            "all_search_history": state.get("all_search_history", []) + [search_result],
            "iteration_count": state.get("iteration_count", 0) + 1,
            "has_tried_rag": bool(
                state.get("has_tried_rag", False) or search_type == "rag"
            ),
            "has_tried_web": bool(
                state.get("has_tried_web", False) or search_type == "web"
            ),
            "consecutive_search_failures": consecutive_search_failures,
            **_base_state_fragment(state),
        }

    async def process_results_node(self, state: ResearchState) -> Dict[str, Any]:
        """Filter, compress, merge results with hybrid strategy + dedup improvements."""
        sr = state.get("search_results") or {}
        docs = sr.get("documents") or []
        if not docs:
            logger.warning("[ProcessResults] No documents found in search result.")
            return {
                "should_retry_query": True,
                "search_results": {},
                **_base_state_fragment(state),
            }

        search_type = sr.get("search_type")
        current_query = sr.get("query")

        overlap_threshold = 0.5

        if search_type == "web":
            source_ids_all = [
                _normalize_url_from_meta(getattr(d, "metadata", {}) or d.metadata)
                for d in docs
            ]
            used_web_urls: List[str] = state.get("used_web_urls", [])
            new_documents = [
                d
                for d, sid in zip(docs, source_ids_all)
                if sid and sid not in set(used_web_urls)
            ]
            overlap = set(source_ids_all) & set(used_web_urls)
            denom = max(len(set(source_ids_all) | set(used_web_urls)), 1)
            ratio = len(overlap) / denom
            if ratio > overlap_threshold:
                logger.warning(
                    f"[ProcessResults] High web source overlap ({ratio:.1%}). Suggest retry with RAG."
                )
                return {
                    "should_retry_query": True,
                    "retry_fallback": "rag",
                    **_base_state_fragment(state),
                }
        else:
            source_ids_all = [
                (getattr(d, "metadata", {}) or d.metadata).get("document_id", "")
                for d in docs
            ]
            used_rag_ids: List[str] = state.get("used_rag_ids", [])
            new_documents = [
                d
                for d, sid in zip(docs, source_ids_all)
                if sid and sid not in set(used_rag_ids)
            ]
            overlap = set(source_ids_all) & set(used_rag_ids)
            denom = max(len(set(source_ids_all) | set(used_rag_ids)), 1)
            ratio = len(overlap) / denom
            if ratio > overlap_threshold:
                logger.warning(
                    f"[ProcessResults] High RAG source overlap ({ratio:.1%}). Suggest retry with Web."
                )
                return {
                    "should_retry_query": True,
                    "retry_fallback": "web",
                    **_base_state_fragment(state),
                }

        if not new_documents:
            logger.warning(
                "[ProcessResults] All documents already used. Suggest switching search type."
            )
            return {"should_retry_query": True, **_base_state_fragment(state)}

        relevant_indices = await citation_agent.ainvoke(
            history=[HumanMessage(content=current_query)], reference=new_documents
        )
        if not relevant_indices or not getattr(relevant_indices, "indexes", None):
            logger.warning(
                "[ProcessResults] Citation agent found no relevant documents (soft fail)."
            )
            return {"should_retry_query": True, **_base_state_fragment(state)}

        idxs = [
            i
            for i in getattr(relevant_indices, "indexes")
            if 0 < i <= len(new_documents)
        ]
        cited_docs = [new_documents[i - 1] for i in idxs]

        citation_start_index = state.get("citation_counter", 0)
        all_cited_docs_so_far = list(state.get("cited_documents", []))
        citation_map = list(state.get("citation_map", []))

        docs_with_markers = []
        current_citation_index = citation_start_index

        for doc in cited_docs:
            meta = getattr(doc, "metadata", {}) or doc.metadata
            doc_copy = doc.model_copy(deep=True) if hasattr(doc, "model_copy") else doc

            page = getattr(doc_copy, "page_content", None)
            if page is None:
                page = getattr(doc_copy, "content", "")
                setattr(
                    doc_copy,
                    "content",
                    f"[CITATION: {current_citation_index}] {page}",
                )
            else:
                doc_copy.page_content = f"[CITATION: {current_citation_index}] {page}"

            docs_with_markers.append(doc_copy)
            all_cited_docs_so_far.append(doc)
            citation_map.append(
                {
                    "index": current_citation_index,
                    "metadata": meta,
                }
            )
            current_citation_index += 1

        accumulated_len = len(state.get("accumulated_knowledge", ""))
        iteration_count = state.get("iteration_count", 0)

        should_consolidate = (
            accumulated_len > 20000 and iteration_count > 1 and iteration_count % 3 == 0
        )

        if should_consolidate and state.get("accumulated_knowledge"):
            new_merged = await compress_agent.ainvoke_with_merge(
                query=current_query,
                new_documents=docs_with_markers,
                existing_knowledge=state["accumulated_knowledge"],
            )
            merged = new_merged if new_merged else state["accumulated_knowledge"]
        else:
            compressed = await compress_agent.ainvoke(
                query=current_query, reference=docs_with_markers
            )
            if state.get("accumulated_knowledge"):
                merged = f"{state['accumulated_knowledge']}\n\n## {current_query}\n\n{compressed}"
            else:
                merged = compressed

        new_rag_ids = list(state.get("used_rag_ids", []))
        new_web_urls = list(state.get("used_web_urls", []))
        if search_type == "rag":
            to_add = [sid for sid in source_ids_all if sid]
            new_rag_ids = list(set(new_rag_ids + to_add))
        else:
            to_add = [
                _normalize_url_from_meta(getattr(d, "metadata", {}) or d.metadata)
                for d in docs
            ]
            to_add = [sid for sid in to_add if sid]
            new_web_urls = list(set(new_web_urls + to_add))

        last_history = list(state.get("all_search_history", []))
        if last_history:
            last_history[-1] = {**last_history[-1], "processed": True}

        return {
            "accumulated_knowledge": merged,
            "used_rag_ids": new_rag_ids,
            "used_web_urls": new_web_urls,
            "search_results": {**sr, "processed": True},
            "all_search_history": last_history,
            "should_retry_query": False,
            "citation_counter": current_citation_index,
            "cited_documents": all_cited_docs_so_far,
            "citation_map": citation_map,
        }

    def decide_after_processing(self, state: ResearchState) -> str:
        """
        Decide next step after processing:
        - If success and not at verify cadence -> continue searching
        - If should verify -> verification
        - If soft failure -> try to enqueue a retry with fallback (in apply_retry node)
        """
        iteration = state.get("iteration_count", 0)
        max_searches = state.get("max_searches", self.max_searches)

        should_verify_this_iteration = (
            iteration % 3 == 0
            or iteration >= max_searches - 2
            or not state.get("pending_queries")
        )

        # If not retry and not forced to verify and still have pending -> continue searching
        if (
            not state.get("should_retry_query")
            and state.get("pending_queries")
            and not should_verify_this_iteration
        ):
            logger.info(
                f"[Router] Skip verification at iteration {iteration}. Continue search."
            )
            return "search_executor"

        # If success (no retry needed) -> verify now
        if not state.get("should_retry_query"):
            return "verification_agent"

        # Soft failure path: prepare fallback retry if usable
        logger.warning(
            "[Router] Soft failure detected. Evaluating retry for the last query."
        )
        last_query = state.get("completed_queries", [])[-1]
        last_type = last_query.get("search_type")
        fallback_type = "web" if last_type == "rag" else "rag"

        # Check usability of fallback
        if fallback_type == "rag":
            if state.get("rag_is_unavailable") or not state.get(
                "is_rag_source_relevant", True
            ):
                logger.warning("[Router] Fallback RAG not usable.")
                # If we still have pending, decide based on cadence
                return (
                    "verification_agent"
                    if should_verify_this_iteration
                    else "search_executor"
                )
        else:
            if state.get("web_is_unavailable"):
                logger.warning("[Router] Fallback Web not usable.")
                return (
                    "verification_agent"
                    if should_verify_this_iteration
                    else "search_executor"
                )

        # Fallback usable -> go to apply_retry node which will mutate pending safely
        return "apply_retry"

    async def apply_retry_node(self, state: ResearchState) -> Dict[str, Any]:
        """Insert a fallback retry query at the front of pending queries. No mutation in router."""
        if not state.get("completed_queries"):
            return {}
        last_query = dict(state["completed_queries"][-1])
        last_type = last_query.get("search_type")
        fallback_type = "web" if last_type == "rag" else "rag"
        pending = list(state.get("pending_queries", []))
        retry_query = {**last_query, "search_type": fallback_type}
        pending.insert(0, retry_query)
        logger.info(
            f"[ApplyRetry] Enqueued retry with {fallback_type.upper()} for '{last_query.get('query')}'."
        )
        return {"pending_queries": pending, "should_retry_query": False}

    async def verification_agent_node(self, state: ResearchState) -> Dict[str, Any]:
        """Verify sufficiency."""
        if state.get("hard_stop"):
            logger.error(
                "[Verification] Hard stop flagged. Skipping verification details."
            )
            return {
                "verification_result": {
                    "is_sufficient": False,
                    "missing_aspects": [state["contextualized_query"]],
                },
                **_base_state_fragment(state),
            }

        if not state.get("accumulated_knowledge"):
            logger.warning(
                "[Verification] No accumulated knowledge to verify. Default insufficient."
            )
            return {
                "verification_result": {
                    "is_sufficient": False,
                    "missing_aspects": [state["contextualized_query"]],
                },
                **_base_state_fragment(state),
            }

        verification_dict = await verification_agent.ainvoke(state)
        logger.info(f"[Verification] Result: {verification_dict}")

        if not verification_dict:
            logger.error(
                "[Verification] Invalid verification response. Default insufficient."
            )
            return {
                "verification_result": {"is_sufficient": False, "missing_aspects": []},
                **_base_state_fragment(state),
            }

        return {"verification_result": verification_dict, **_base_state_fragment(state)}

    async def reflection_node(self, state: ResearchState) -> Dict[str, Any]:
        """Critique current research state and suggest next steps."""
        reflection_result = await reflection_agent.ainvoke(state)
        if not reflection_result:
            logger.error("[Reflection] Failed to generate a valid reflection.")
            return {
                "reflection_result": {"critique": "N/A", "next_steps": "N/A"},
                **_base_state_fragment(state),
            }

        return {
            "reflection_result": reflection_result,
            **_base_state_fragment(state),
        }

    async def dynamic_query_generator_node(
        self, state: ResearchState
    ) -> Dict[str, Any]:
        """Generate dynamic queries with search history awareness."""
        dynamic_query_generator_dict = await dynamic_query_agent.ainvoke(state)

        if not dynamic_query_generator_dict:
            logger.error(
                "[DynamicQueryGenerator] Failed to generate valid dynamic queries."
            )
            return {"pending_queries": [], **_base_state_fragment(state)}

        new_queries = dynamic_query_generator_dict.get("queries", [])
        if not new_queries:
            logger.warning("[DynamicQueryGenerator] Agent returned empty queries.")
            return {"pending_queries": [], **_base_state_fragment(state)}

        # normalize to dict
        pending = [_as_dict_query(q) for q in new_queries]
        return {"pending_queries": pending, **_base_state_fragment(state)}

    def route_after_dynamic_generation(self, state: ResearchState) -> str:
        """Decides where to go after attempting to generate new queries."""
        if state.get("pending_queries"):
            logger.info(
                "[Router] New queries generated. Proceeding to search_executor."
            )
            return "search_executor"
        else:
            logger.error(
                "[Router] Failed to generate new queries. Terminating process."
            )
            return "__end__"

    def route_after_verification(self, state: ResearchState) -> str:
        """Smart routing based on verification + pending queries analysis + hard stop."""
        # Hard stop or too many failures -> END
        if (
            state.get("hard_stop")
            or state.get("consecutive_search_failures", 0)
            >= self.max_consecutive_failures
        ):
            logger.error(
                "[Router] Hard stop or exceeded max consecutive search failures → END"
            )
            return "__end__"

        iteration = state.get("iteration_count", 0)
        max_searches = state.get("max_searches", self.max_searches)
        if iteration >= max_searches:
            logger.info("[Router] Max iterations reached → END")
            return "__end__"

        verification = state.get("verification_result")
        if not verification:
            logger.warning("[Router] No verification result → END")
            return "__end__"

        if verification.get("is_sufficient"):
            logger.info("[Router] Knowledge is sufficient. Ending.")
            return "__end__"

        # If both channels are unavailable now, no point continuing
        if state.get("rag_is_unavailable") and state.get("web_is_unavailable"):
            logger.error("[Router] Both RAG and Web unavailable → END")
            return "__end__"

        if state.get("pending_queries"):
            logger.info(
                "[Router] Pending queries exist. Continuing with planned search."
            )
            return "search_executor"

        return "reflection_node"

    # ------------------------------------------------------------------------------------
    # GRAPH WIRING
    # ------------------------------------------------------------------------------------

    def _build_graph(self) -> CompiledStateGraph:
        """Build research graph"""
        workflow = StateGraph(ResearchState)

        workflow.add_node("query_planner", self.query_planner_node)
        workflow.add_node("pre_flight_rag_check", self.pre_flight_rag_check_node)
        workflow.add_node("search_executor", self.search_executor_node)
        workflow.add_node("process_results", self.process_results_node)
        workflow.add_node("apply_retry", self.apply_retry_node)
        workflow.add_node("verification_agent", self.verification_agent_node)
        workflow.add_node("dynamic_query_generator", self.dynamic_query_generator_node)
        workflow.add_node("handle_no_plan", self.handle_no_plan_node)
        workflow.add_node("reflection_node", self.reflection_node)

        workflow.set_entry_point("query_planner")

        workflow.add_conditional_edges(
            "query_planner",
            self.decide_after_planner,
            {
                "pre_flight_rag_check": "pre_flight_rag_check",
                "handle_no_plan": "handle_no_plan",
            },
        )

        workflow.add_edge("pre_flight_rag_check", "search_executor")
        workflow.add_edge("handle_no_plan", "dynamic_query_generator")
        workflow.add_edge("search_executor", "process_results")

        # process_results → (apply_retry | verification_agent | search_executor)
        workflow.add_conditional_edges(
            "process_results",
            self.decide_after_processing,
            {
                "search_executor": "search_executor",
                "verification_agent": "verification_agent",
                "apply_retry": "apply_retry",
            },
        )
        # after apply_retry, go back to search
        workflow.add_edge("apply_retry", "search_executor")

        workflow.add_edge("reflection_node", "dynamic_query_generator")

        workflow.add_conditional_edges(
            "dynamic_query_generator",
            self.route_after_dynamic_generation,
            {
                "search_executor": "search_executor",
                "__end__": END,
            },
        )

        workflow.add_conditional_edges(
            "verification_agent",
            self.route_after_verification,
            {
                "search_executor": "search_executor",
                "reflection_node": "reflection_node",
                "__end__": END,
            },
        )

        return workflow.compile(name=self.graph_name)
