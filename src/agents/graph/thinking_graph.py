# src/agents/graph/research_graph.py
from __future__ import annotations

from typing import Any, Dict

from langgraph.graph import StateGraph
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
    Iterative Research Graph with Reflection.

    Flow:
    1. Generate Direction → Decide Action Route
    2a. If "use_tool": Execute Subgraph → Extract Learnings
    2b. If "reason_only": Pure Reasoning (no tool call)
    3. Evaluate Sufficiency
    4. If insufficient: Continue → back to step 1
    5. If sufficient: Synthesize Response → END

    Response Mode Selection:
    - If has_tool_results=True: Use ADVANCE (with citations)
    - If has_tool_results=False: Use REASONING_ONLY (no citations needed)

    Safety: max_iterations prevents infinite loops
    """

    def __init__(self):
        super().__init__()
        self.graph_name = "ThinkingGraph"
        self.compiled_graph = self._build_graph()
        self.max_iterations = 30
        self.min_knowledge_threshold = 500

    @property
    def graph(self) -> CompiledStateGraph:
        return self.compiled_graph

    def default_run_config(self) -> RunConfig:
        return RunConfig(
            graph_name=self.graph_name,
            recursion_limit=100,
            timeout_seconds=300,
        )

    async def generate_direction_node(self, state: ThinkingState) -> Dict[str, Any]:
        """
        Generate next research direction using reflection_agent.
        Returns: current_direction, action, selected_subgraph, reasoning
        """
        conversation = state.get("conversation", [])

        try:
            resp = await reflection_agent.ainvoke(state=state)
            direction = resp.get("query", conversation[-1].content)
            action = resp.get("action", "use_tool")
            selected_subgraph = resp.get("subgraph", "web_search")
            reasoning = resp.get("reasoning", "")

            logger.info(
                f"[Direction] Iter={state.get('iteration_count', 0)}, Action={action}, Query={direction[:100]}..."
            )

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
        """Route based on action: 'use_tool' or 'reason_only'."""
        action = state.get("action", "use_tool")

        if action == "reason_only":
            logger.info("[Route] → Pure Reasoning")
            return "reason"
        else:
            logger.info("[Route] → Execute Subgraph")
            return "execute"

    async def execute_subgraph_node(self, state: ThinkingState) -> Dict[str, Any]:
        """
        Execute selected subgraph and return documents.

        Special handling:
        - SQL subgraph: Store result in _sql_result, set response_mode
        - Other subgraphs: Deduplicate and return documents
        """
        subgraph_name = state.get("selected_subgraph")
        query = state.get("current_direction")

        if not subgraph_name:
            logger.error("[Execute] No subgraph selected")
            return {"_temp_documents": []}

        try:
            subgraph_config = SubgraphRegistry.get_profile(subgraph_name)
            if not subgraph_config:
                logger.error(f"[Execute] Subgraph '{subgraph_name}' not found")
                return {"_temp_documents": []}

            exec_ref = subgraph_config.executor
            executor = (
                EXECUTORS.get(exec_ref) if isinstance(exec_ref, str) else exec_ref
            )

            if not executor or not callable(executor):
                logger.error(f"[Execute] Executor for '{subgraph_name}' not callable")
                return {"_temp_documents": []}

            logger.info(f"[Execute] {subgraph_name}: {query}")

            result_obj: SubgraphOutput = await executor(state)

            if subgraph_name == "sql_query":
                sql_result = (
                    result_obj.main_context or "No SQL execution results available."
                )
                logger.info(
                    f"[Execute] SQL query executed, result length: {len(sql_result)}"
                )

                return {
                    "_sql_result": sql_result,
                    "_is_sql_iteration": True,
                    "has_tool_results": True,
                }

            documents = result_obj.cited_documents or []
            logger.info(f"[Execute] Retrieved {len(documents)} documents")

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
                f"[Execute] {len(new_docs)}/{len(documents)} new documents after dedup"
            )

            new_docs = truncate_docs_by_tokens(
                new_docs, max_tokens=8192, tokenizer=self.tokenizer
            )

            return {
                "_temp_documents": new_docs,
                "used_rag_ids": list(used_rag_ids),
                "used_web_urls": list(used_web_urls),
                "has_tool_results": True,
            }

        except Exception as e:
            logger.error(f"[Execute] Error: {e}")
            return {"_temp_documents": []}

    async def pure_reasoning_node(self, state: ThinkingState) -> Dict[str, Any]:
        """
        Pure reasoning path - no tool execution.
        Append reasoning to accumulated_knowledge and learnings.
        """
        reasoning = state.get("reasoning", "")
        iteration = state.get("iteration_count", 0)

        if not reasoning:
            logger.warning("[Reasoning] No reasoning content provided")
            return {}

        logger.info(f"[Reasoning] Iter {iteration}: {reasoning[:150]}...")

        learning_entry = f"[Iter {iteration}] Pure reasoning: {reasoning[:300]}{'...' if len(reasoning) > 300 else ''}"

        learnings = list(state.get("learnings", []))
        learnings.append(learning_entry)

        accumulated = state.get("accumulated_knowledge", "")
        accumulated += f"\n\n## Reasoning (Iteration {iteration})\n\n{reasoning}"

        return {
            "learnings": learnings,
            "accumulated_knowledge": accumulated,
        }

    async def extract_learnings_node(self, state: ThinkingState) -> Dict[str, Any]:
        """
        Process results from execute_subgraph_node.

        Two paths:
        1. SQL result: Just store the SQL result in accumulated_knowledge
        2. Document results: Add citations, compress, store
        """
        iteration = state.get("iteration_count", 0)
        query = state.get("current_direction", "")
        subgraph_name = state.get("selected_subgraph", "unknown")

        if state.get("_is_sql_iteration", False):
            sql_result = state.get("_sql_result", "")

            if not sql_result:
                logger.warning("[Learnings] SQL iteration but no result")
                return {}

            preview = sql_result[:250] + "..." if len(sql_result) > 250 else sql_result
            learning_entry = f"[Iter {iteration}] SQL query executed for '{query}'. Result: {preview}"

            learnings = list(state.get("learnings", []))
            learnings.append(learning_entry)

            accumulated = state.get("accumulated_knowledge", "")
            accumulated += f"\n\n## SQL Query Result (Iteration {iteration})\n\nQuery: {query}\n\n{sql_result}"

            logger.info(f"[Learnings] SQL result stored, {len(sql_result)} chars")

            return {
                "learnings": learnings,
                "accumulated_knowledge": accumulated,
                "_is_sql_iteration": False,
            }

        docs = state.get("_temp_documents", [])
        if not docs:
            logger.warning("[Learnings] No documents to process")
            return {}

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
                query=query,
                reference=docs_with_citations,
            )
        except Exception as e:
            logger.error(f"[Learnings] Compression failed: {e}")
            compressed = "\n\n".join([d.page_content for d in docs_with_citations])

        preview = compressed[:250] + "..." if len(compressed) > 250 else compressed
        learning_entry = f"[Iter {iteration}] {subgraph_name} for '{query}': Found {len(docs)} docs. Preview: {preview}"

        learnings = list(state.get("learnings", []))
        learnings.append(learning_entry)

        accumulated = state.get("accumulated_knowledge", "")
        accumulated += f"\n\n## {query} (Iteration {iteration})\n\n{compressed}"

        logger.info(
            f"[Learnings] Extracted from {len(docs)} documents, {len(compressed)} chars"
        )

        return {
            "learnings": learnings,
            "accumulated_knowledge": accumulated,
            "citation_counter": current_citation,
            "cited_documents": cited_documents,
            "citation_map": citation_map,
        }

    async def evaluate_sufficiency_node(self, state: ThinkingState) -> Dict[str, Any]:
        """
        Evaluate if research is sufficient using verification_agent.
        Returns: _should_continue, _missing_aspects

        Safety checks:
        - Max iterations reached → stop
        - Insufficient knowledge length → continue
        - Otherwise, ask verification_agent
        """
        knowledge = state.get("accumulated_knowledge", "")
        iteration = state.get("iteration_count", 0)

        if iteration >= self.max_iterations:
            logger.warning(
                f"[Evaluate] Max iterations ({self.max_iterations}) reached. STOPPING."
            )
            return {
                "_should_continue": False,
                "_missing_aspects": "",
            }

        if not knowledge or len(knowledge) < self.min_knowledge_threshold:
            logger.info(
                f"[Evaluate] Knowledge too short ({len(knowledge)} chars). CONTINUE."
            )
            return {
                "_should_continue": True,
                "_missing_aspects": "Insufficient knowledge gathered.",
            }

        try:
            resp = await verification_agent.ainvoke(state=state)
            is_sufficient = resp.get("is_sufficient", False)
            missing = resp.get("missing_aspects", "")

            logger.info(f"[Evaluate] Iteration {iteration}: Sufficient={is_sufficient}")
            if missing:
                logger.info(f"[Evaluate] Missing: {missing}")

            return {
                "_should_continue": not is_sufficient,
                "_missing_aspects": missing,
            }

        except Exception as e:
            logger.error(f"[Evaluate] Verification failed: {e}")
            return {
                "_should_continue": iteration < 2,
                "_missing_aspects": "Evaluation failed, continuing cautiously.",
            }

    def decide_continue_or_synthesize(self, state: ThinkingState) -> str:
        """Route based on _should_continue flag."""
        should_continue = state.get("_should_continue", False)

        if should_continue:
            logger.info("[Route] → Continue Iteration")
            return "continue"
        else:
            logger.info("[Route] → Synthesize Response")
            return "synthesize"

    async def continue_iteration_node(self, state: ThinkingState) -> Dict[str, Any]:
        """Increment iteration counter."""
        current = state.get("iteration_count", 0)
        logger.info(f"[Continue] Starting iteration {current + 1}")

        return {
            "iteration_count": current + 1,
        }

    async def synthesize_response_node(self, state: ThinkingState) -> Dict[str, Any]:
        """
        Finalize research and generate response.

        Response Mode Selection Priority:
        1. Has SQL + Documents → ADVANCE (citations needed, SQL is part of context)
        2. Has SQL only → SQL_RESPONSE (special SQL formatting, no citations)
        3. Has Documents only → ADVANCE (research synthesis with citations)
        4. Pure reasoning only → REASONING_ONLY (no citations)
        """
        iteration_count = state.get("iteration_count", 0)
        citation_counter = state.get("citation_counter", 0)

        has_sql = any(
            isinstance(line, str) and "SQL query executed" in line
            for line in state.get("learnings", [])
        )

        has_documents = citation_counter > 0
        has_tool_results = state.get("has_tool_results", False)

        if has_sql and has_documents:
            response_mode = ResponseMode.ADVANCE
            logger.info("[Synthesize] Using ADVANCE mode (mixed: SQL + documents)")
        elif has_sql:
            response_mode = ResponseMode.SQL_RESPONSE
            logger.info("[Synthesize] Using SQL_RESPONSE mode (SQL only)")
        elif has_documents or has_tool_results:
            response_mode = ResponseMode.ADVANCE
            logger.info("[Synthesize] Using ADVANCE mode (documents only)")
        else:
            response_mode = ResponseMode.REASONING_ONLY
            logger.info("[Synthesize] Using REASONING_ONLY mode (pure reasoning)")

        synthesis_state = dict(state)
        synthesis_state["response_mode"] = response_mode

        try:
            resp = await response_agent.ainvoke(synthesis_state)
            resp_metadata = resp.response_metadata or {}
            resp_metadata["total_iterations"] = iteration_count
            resp_metadata["total_citations"] = citation_counter
            resp_metadata["response_mode"] = response_mode
            resp_metadata["has_sql"] = has_sql
            resp_metadata["has_documents"] = has_documents

            logger.info(
                f"[Synthesize] Complete. {iteration_count} iterations, "
                f"{citation_counter} citations, mode={response_mode}"
            )

            return {
                "final_answer": resp.content,
                "response_metadata": resp_metadata,
            }

        except Exception as e:
            logger.error(f"[Synthesize] Failed: {e}")
            return {
                "final_answer": "I apologize, but I encountered an error while synthesizing the response.",
                "response_metadata": {"error": str(e)},
            }

    def _build_graph(self) -> CompiledStateGraph:
        """Build the thinking graph workflow."""
        workflow = StateGraph(ThinkingState)

        workflow.add_node("generate_direction", self.generate_direction_node)
        workflow.add_node("execute_subgraph", self.execute_subgraph_node)
        workflow.add_node("pure_reasoning", self.pure_reasoning_node)
        workflow.add_node("extract_learnings", self.extract_learnings_node)
        workflow.add_node("evaluate_sufficiency", self.evaluate_sufficiency_node)
        workflow.add_node("continue_iteration", self.continue_iteration_node)
        workflow.add_node("synthesize_response", self.synthesize_response_node)

        workflow.set_entry_point("generate_direction")

        workflow.add_conditional_edges(
            "generate_direction",
            self.decide_action_route,
            {
                "execute": "execute_subgraph",
                "reason": "pure_reasoning",
            },
        )

        workflow.add_edge("execute_subgraph", "extract_learnings")
        workflow.add_edge("extract_learnings", "evaluate_sufficiency")

        workflow.add_edge("pure_reasoning", "evaluate_sufficiency")

        workflow.add_conditional_edges(
            "evaluate_sufficiency",
            self.decide_continue_or_synthesize,
            {
                "continue": "continue_iteration",
                "synthesize": "synthesize_response",
            },
        )

        workflow.add_edge("continue_iteration", "generate_direction")

        workflow.set_finish_point("synthesize_response")

        return workflow.compile(name=self.graph_name)
