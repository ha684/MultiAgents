# src/agents/graph/research_graph.py
from __future__ import annotations

from typing import Any, Dict
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import tiktoken
from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.basic import citation_agent, compress_agent
from src.agents.graph.base import GraphAgentBase
from src.agents.tools.server.mcp_retrieve_tools import rag_search, web_search
from src.domain.entities.graph import RunConfig
from src.domain.entities.state import ResearchState
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


def _truncate_docs_by_tokens(documents: list, max_tokens: int, tokenizer) -> list:
    """Truncate documents to fit within token budget."""
    if not documents:
        return []

    texts = [doc.page_content for doc in documents]
    encoded = tokenizer.encode_batch(text=texts, num_threads=4)
    total_tokens = sum(len(tokens) for tokens in encoded)

    if total_tokens <= max_tokens:
        return documents

    # Proportional allocation
    final_docs = []
    doc_tokens = [len(tokens) for tokens in encoded]
    allocated = [int(max_tokens * (dt / total_tokens)) for dt in doc_tokens]

    for i, doc in enumerate(documents):
        if allocated[i] < 50:  # Skip very small allocations
            continue
        if doc_tokens[i] <= allocated[i]:
            final_docs.append(doc)
        else:
            ratio = allocated[i] / doc_tokens[i]
            content = doc.page_content
            truncated = type(doc)(
                page_content=content[: int(len(content) * ratio)] + "...",
                metadata=doc.metadata,
            )
            final_docs.append(truncated)

    logger.info(
        f"Truncated {len(documents)} docs ({total_tokens} tokens) to {len(final_docs)} docs (~{max_tokens} tokens)"
    )
    return final_docs


class ResearchGraph(GraphAgentBase[ResearchState]):
    """
    Simplified Research Graph - Efficient depth-based search like ChatGPT.

    Flow:
    1. Initialize → Generate Direction → Execute Searches → Extract Learnings
    2. Check Depth: if depth > 0, generate next direction and repeat
    3. If depth = 0, finalize and return
    """

    def __init__(self):
        super().__init__()
        self.graph_name = "ResearchGraph"
        self.compiled_graph = self._build_graph()
        self.tokenizer = tiktoken.encoding_for_model("gpt-4o")
        self.default_breadth = 2  # Searches per depth level
        self.default_depth = 2  # Depth iterations
        logger.info("ResearchGraph initialized (refactored for efficiency).")

    @property
    def graph(self) -> CompiledStateGraph:
        return self.compiled_graph

    def default_run_config(self) -> RunConfig:
        return RunConfig(
            graph_name=self.graph_name, recursion_limit=30, timeout_seconds=300
        )

    async def initialize_node(self, state: ResearchState) -> ResearchState:
        """Initialize research parameters and check source availability."""
        breadth = state.get("breadth", self.default_breadth)
        depth = state.get("depth", self.default_depth)

        # Quick check for source availability
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
            "depth": depth,
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
        learnings = state.get("learnings", [])
        knowledge = state.get("accumulated_knowledge", "")

        if depth_level == 0:
            # First iteration - start with main query
            direction = query
            thinking = f"Investigating: {query}"
        else:
            # Subsequent iterations - analyze what we've learned and what's missing
            from langchain_core.prompts import ChatPromptTemplate

            from src.core.config.llm_config import get_llm

            llm = get_llm("llm")

            prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        """You are a research assistant helping to direct deep research.

Based on what we've learned so far, identify the MOST IMPORTANT next direction to explore.

Guidelines:
- Focus on ONE specific aspect or question
- Build on previous learnings
- Address gaps in understanding
- Be concrete and specific

Return a JSON with:
- "direction": A focused question or topic to explore next
- "thinking": Brief note about why this direction (like "Looking into..." or "Considering...")
""",
                    ),
                    (
                        "human",
                        """Original Query: {query}

Previous Learnings:
{learnings}

Current Knowledge:
{knowledge}

What should we explore next?""",
                    ),
                ]
            )

            try:
                response = await llm.bind(
                    response_format={"type": "json_object"}
                ).ainvoke(
                    prompt.format_messages(
                        query=query,
                        learnings="\n".join(
                            f"- {learning}" for learning in learnings[-3:]
                        )
                        if learnings
                        else "None yet",
                        knowledge=knowledge[-2000:] if knowledge else "None yet",
                    )
                )

                import json

                result = json.loads(response.content)
                direction = result.get("direction", query)
                thinking = result.get("thinking", f"Exploring next aspect of: {query}")
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

        # Determine search strategy: alternate between RAG and Web for diversity
        searches_to_perform = []
        search_count = state.get("search_count", 0)

        for i in range(breadth):
            # Alternate: even indices use RAG (if available), odd use Web
            if i % 2 == 0 and rag_available:
                searches_to_perform.append("rag")
            elif web_available:
                searches_to_perform.append("web")
            elif rag_available:
                searches_to_perform.append("rag")

        all_documents = []
        search_history = list(state.get("search_history", []))

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
                "search_count": search_count + breadth,
                "search_history": search_history,
            }

        # Deduplicate
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
            new_docs = all_documents[:breadth]  # Use some anyway

        logger.info(f"After dedup: {len(new_docs)}/{len(all_documents)} documents")

        # Filter by relevance using citation agent
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

        # Truncate if too long
        new_docs = _truncate_docs_by_tokens(
            new_docs, max_tokens=6000, tokenizer=self.tokenizer
        )

        return {
            "search_count": search_count + breadth,
            "search_history": search_history,
            "used_rag_ids": list(used_rag_ids),
            "used_web_urls": list(used_web_urls),
            "_temp_documents": new_docs,  # Pass to next node
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

        # Add citation markers
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

        # Compress/summarize the findings
        try:
            compressed = await compress_agent.ainvoke(
                query=direction, reference=docs_with_citations
            )
        except Exception as e:
            logger.error(f"Compression failed: {e}")
            compressed = "\n\n".join([d.page_content for d in docs_with_citations[:3]])

        # Extract key learning point
        learning_point = f"[Depth {state.get('current_depth_level', 0)}] {state.get('thinking_notes', '')}: {compressed[:200]}..."

        # Merge into accumulated knowledge
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

    def check_depth_node(self, state: ResearchState) -> str:
        """
        Decide if we should continue to next depth level or finish.
        """
        remaining_depth = state.get("depth", 0)
        current_level = state.get("current_depth_level", 0)

        if remaining_depth > 0:
            logger.info(f"[Depth Check] Continuing to depth level {current_level + 1}")
            return "continue"
        else:
            logger.info("[Depth Check] Research complete, finalizing")
            return "finalize"

    async def continue_depth_node(self, state: ResearchState) -> Dict[str, Any]:
        """Prepare for next depth iteration."""
        return {
            "depth": state.get("depth", 0) - 1,
            "current_depth_level": state.get("current_depth_level", 0) + 1,
        }

    async def finalize_node(self, state: ResearchState) -> Dict[str, Any]:
        """Final preparation of research results."""
        logger.info("[Finalize] Research complete")
        logger.info(f"Total searches: {state.get('search_count', 0)}")
        logger.info(f"Total citations: {state.get('citation_counter', 0)}")
        logger.info(f"Depth levels completed: {state.get('current_depth_level', 0)}")

        return {}

    def _build_graph(self) -> CompiledStateGraph:
        """Build the simplified research graph."""
        workflow = StateGraph(ResearchState)

        # Add nodes
        workflow.add_node("initialize", self.initialize_node)
        workflow.add_node("generate_direction", self.generate_direction_node)
        workflow.add_node("execute_searches", self.execute_searches_node)
        workflow.add_node("extract_learnings", self.extract_learnings_node)
        workflow.add_node("continue_depth", self.continue_depth_node)
        workflow.add_node("finalize", self.finalize_node)

        # Set entry point
        workflow.set_entry_point("initialize")

        # Linear flow for main loop
        workflow.add_edge("initialize", "generate_direction")
        workflow.add_edge("generate_direction", "execute_searches")
        workflow.add_edge("execute_searches", "extract_learnings")

        # Conditional: check if we should continue or finish
        workflow.add_conditional_edges(
            "extract_learnings",
            self.check_depth_node,
            {
                "continue": "continue_depth",
                "finalize": "finalize",
            },
        )

        # Loop back for next depth iteration
        workflow.add_edge("continue_depth", "generate_direction")

        # End
        workflow.add_edge("finalize", END)

        return workflow.compile(name=self.graph_name)
