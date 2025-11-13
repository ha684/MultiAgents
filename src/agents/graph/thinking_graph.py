# src/agents/graph/research_graph.py
from __future__ import annotations

from typing import Any, Dict

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.basic import (
    compress_agent,
    reflection_agent,
    response_agent,
    verification_agent,
)
from src.agents.executors import EXECUTORS
from src.agents.graph.base import GraphAgentBase
from src.agents.shared.registry import SubgraphRegistry
from src.domain.entities.graph import ResponseMode, RunConfig, SubgraphOutput
from src.domain.entities.state import ThinkingState
from src.utils import normalize_url, truncate_docs_by_tokens
from src.utils.logger_conf import logger


class ThinkingGraph(GraphAgentBase[ThinkingState]):
    """
    Adaptive Thinking Graph - Agentic thinking with dynamic evaluation like ChatGPT.

    Flow:
    1. Initialize → Generate Direction → Execute Searches → Extract Learnings
    2. Evaluate Sufficiency: Agent decides if research is adequate or needs more
    3. If insufficient, generate next direction and repeat; if sufficient, finalize
    4. Safety limit: max_iterations to prevent infinite loops
    """

    def __init__(self):
        super().__init__()
        self.graph_name = "ThinkingGraph"
        self.compiled_graph = self._build_graph()
        self.default_breadth = 2
        self.max_iterations = 30
        self.min_knowledge_threshold = 500

    @property
    def graph(self) -> CompiledStateGraph:
        return self.compiled_graph

    def default_run_config(self) -> RunConfig:
        return RunConfig(
            graph_name=self.graph_name, recursion_limit=100, timeout_seconds=300
        )

    async def generate_direction_node(self, state: ThinkingState) -> Dict[str, Any]:
        """
        Generate focused research direction for current depth level.
        Similar to ChatGPT's progressive thinking.
        """
        conversation = state.get("conversation", [])
        state["conversation"] = conversation

        try:
            resp = await reflection_agent.ainvoke(state=state)
            direction = resp.get("query", conversation[-1].content)
            action = resp.get("action", "use_tool")
            selected_subgraph = resp.get("subgraph", "web_search")
            reasoning = resp.get("reasoning", "")

        except Exception as e:
            logger.error(f"Failed to generate direction: {e}")
            direction = conversation[-1].content
            action = "use_tool"
            selected_subgraph = "web_search"
            reasoning = ""
        return {
            "current_direction": direction,
            "action": action,
            "selected_subgraph": selected_subgraph,
            "reasoning": reasoning,
        }

    def decide_action_route(self, state: ThinkingState) -> str:
        """Route based on action in direction."""
        direction = state.get("current_direction", {})
        action = direction.get("action")

        if action == "use_tool":
            return "execute"
        elif action == "reason_only":
            return "reason"
        else:
            logger.warning(f"Unknown action: {action}, defaulting to execute")
            return "execute"

    async def execute_subgraph_node(self, state: ThinkingState) -> Dict[str, Any]:
        """Execute selected subgraph and return documents."""
        subgraph_name = state.get("selected_subgraph")
        query = state.get("current_direction")

        if not subgraph_name:
            logger.error("[Thinking] No subgraph selected")
            return {"_temp_documents": []}

        try:
            subgraph_config = SubgraphRegistry.get_profile(subgraph_name)

            if not subgraph_config:
                logger.error(f"[Thinking] Subgraph '{subgraph_name}' not found")
                return {"_temp_documents": []}

            exec_ref = subgraph_config.executor
            executor = (
                EXECUTORS.get(exec_ref) if isinstance(exec_ref, str) else exec_ref
            )

            if not executor or not callable(executor):
                logger.error(f"[Thinking] Executor for '{subgraph_name}' not callable")
                return {"_temp_documents": []}

            execution_state = dict(state)
            execution_state["contextualized_query"] = query

            logger.info(f"[Thinking] Executing {subgraph_name}: {query}")

            result_obj: SubgraphOutput = await executor(execution_state)
            documents = result_obj.cited_documents or []

            if not documents and result_obj.main_context:
                logger.warning(
                    f"[Thinking] {subgraph_name} returned context but no documents"
                )

            logger.info(
                f"[Thinking] {subgraph_name} returned {len(documents)} documents"
            )

            used_rag_ids = set(state.get("used_rag_ids", []))
            used_web_urls = set(state.get("used_web_urls", []))

            new_docs = []
            for doc in documents:
                meta = doc.metadata
                doc_id = meta.get("document_id")
                url = normalize_url(meta)

                if doc_id and doc_id in used_rag_ids:
                    continue
                if url and url in used_web_urls:
                    continue

                new_docs.append(doc)
                if doc_id:
                    used_rag_ids.add(doc_id)
                if url:
                    used_web_urls.add(url)

            logger.info(
                f"[Thinking] {len(new_docs)}/{len(documents)} new documents after dedup"
            )

            new_docs = truncate_docs_by_tokens(
                new_docs, max_tokens=8192, tokenizer=self.tokenizer
            )

            return {
                "_temp_documents": new_docs,
                "used_rag_ids": list(used_rag_ids),
                "used_web_urls": list(used_web_urls),
            }

        except Exception as e:
            logger.error(f"[Thinking] Error executing {subgraph_name}: {e}")
            return {"_temp_documents": []}

    async def pure_reasoning_node(self, state: ThinkingState) -> Dict[str, Any]:
        """
        Pure reasoning - no tool execution.
        Store reasoning in learnings.
        """
        reasoning = state.get("reasoning", "")

        if not reasoning:
            logger.warning("No reasoning provided in direction")
            return {}

        logger.info(f"[Pure Reasoning] {reasoning[:200]}...")

        learnings = list(state.get("learnings", []))
        learnings.append(
            {
                "type": "reasoning",
                "content": reasoning,
            }
        )

        accumulated = state.get("accumulated_knowledge", "")
        accumulated += f"\n\n## Reasoning\n\n{reasoning}"

        return {
            "learnings": learnings,
            "accumulated_knowledge": accumulated,
        }

    async def extract_learnings_node(self, state: ThinkingState) -> Dict[str, Any]:
        """
        Process search results to extract learnings.
        Add citations and compress into accumulated knowledge.
        """
        docs = state.get("_temp_documents", [])
        if not docs or state.get("action", "use_tool") == "reason_only":
            logger.warning("No documents to process")
            return {}

        query = state.get("current_direction", "")

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
                query=query, reference=docs_with_citations
            )
        except Exception as e:
            logger.error(f"Compression failed: {e}")
            compressed = "\n\n".join([d.page_content for d in docs_with_citations])

        learnings = list(state.get("learnings", []))
        learnings.append(
            {
                "type": "search",
                "subgraph": state.get("selected_subgraph", "web_search"),
                "query": query,
                "content": compressed[:200] + "...",
            }
        )

        accumulated = state.get("accumulated_knowledge", "")
        accumulated += f"\n\n## {query}\n\n{compressed}"

        logger.info(f"[Learnings] Extracted from {len(docs)} documents")

        return {
            "learnings": learnings,
            "accumulated_knowledge": accumulated,
            "citation_counter": current_citation,
            "cited_documents": cited_documents,
            "citation_map": citation_map,
        }

    async def evaluate_sufficiency_node(self, state: ThinkingState) -> Dict[str, Any]:
        """
        Evaluate if current research is sufficient.
        Returns: is_sufficient, missing_aspects
        """
        knowledge = state.get("accumulated_knowledge", "")
        iteration = state.get("iteration_count", 0)

        if iteration >= self.max_iterations:
            logger.warning(f"Max iterations ({self.max_iterations}) reached.")
            return {"_should_continue": False}

        if not knowledge or len(knowledge) < self.min_knowledge_threshold:
            logger.info("Insufficient knowledge. Continue research.")
            return {"_should_continue": True}

        try:
            resp = await verification_agent.ainvoke(state=state)
            is_sufficient = resp.get("is_sufficient", False)
            missing = resp.get("missing_aspects", "")

            logger.info(f"[Evaluate] Sufficient: {is_sufficient}")
            if missing:
                logger.info(f"[Evaluate] Missing: {missing}")

            return {
                "missing_aspects": missing,
                "_should_continue": not is_sufficient,
            }

        except Exception as e:
            logger.error(f"Evaluation failed: {e}")
            return {"_should_continue": iteration < 2}

    def decide_continue_or_synthesize(self, state: ThinkingState) -> str:
        """Route based on evaluation."""
        should_continue = state.get("_should_continue", False)
        return "continue" if should_continue else "synthesize_response"

    async def continue_iteration_node(self, state: ThinkingState) -> Dict[str, Any]:
        """Increment iteration counter."""
        return {
            "iteration_count": state.get("iteration_count", 0) + 1,
        }

    async def synthesize_response(self, state: ThinkingState) -> Dict[str, Any]:
        """Finalize research."""
        response_mode = ResponseMode.ADVANCE
        state["response_mode"] = response_mode
        resp = await response_agent.ainvoke(state=state)
        return {
            "final_answer": resp.content,
        }

    def _build_graph(self) -> CompiledStateGraph:
        """Build the research graph."""
        workflow = StateGraph(ThinkingState)

        workflow.add_node("generate_direction", self.generate_direction_node)
        workflow.add_node("decide_action_route", self.decide_action_route)
        workflow.add_node("execute_subgraph", self.execute_subgraph_node)
        workflow.add_node("pure_reasoning", self.pure_reasoning_node)
        workflow.add_node("extract_learnings", self.extract_learnings_node)
        workflow.add_node("evaluate_sufficiency", self.evaluate_sufficiency_node)
        workflow.add_node("continue_iteration", self.continue_iteration_node)
        workflow.add_node("synthesize_response", self.synthesize_response)

        workflow.set_entry_point("generate_direction")
        workflow.add_edge("generate_direction", "decide_action_route")

        workflow.add_conditional_edges(
            "decide_action_route",
            self.decide_action_route,
            {
                "execute": "execute_subgraph",
                "reason": "pure_reasoning",
            },
        )

        workflow.add_edge("execute_subgraph", "extract_learnings")
        workflow.add_edge("pure_reasoning", "evaluate_sufficiency")
        workflow.add_edge("extract_learnings", "evaluate_sufficiency")

        workflow.add_conditional_edges(
            "evaluate_sufficiency",
            self.decide_continue_or_synthesize,
            {
                "continue": "continue_iteration",
                "synthesize_response": "synthesize_response",
            },
        )

        workflow.add_edge("continue_iteration", "generate_direction")

        workflow.add_edge("synthesize_response", END)

        return workflow.compile(name=self.graph_name)
