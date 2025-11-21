# src/agents/graph/normal_graph.py
"""
Normal Graph - Fast Path for Straightforward Queries
Linear flow: Phase Planning → Action Execution → Execute Subgraph → Synthesize Response
"""

from typing import Any

from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.basic import action_execution_agent, phase_agent, response_agent
from src.agents.executors import EXECUTORS
from src.agents.graph.base import GraphAgentBase
from src.agents.shared.registry import SubgraphRegistry
from src.domain.entities.graph import ResponseMode, RunConfig, SubgraphOutput
from src.domain.entities.state import NormalGraphState
from src.utils import (
    format_context_for_response,
    truncate_docs_by_tokens,
)
from src.utils.logger_conf import logger


class NormalGraph(GraphAgentBase[NormalGraphState]):
    """
    Normal Graph - Fast Path for Clear Queries

    Flow:
    1. Phase Planning: Decide phase title and action type (normal mode, balanced)
    2. Action Execution: Either reason directly OR select tool + generate query
    3. Execute Subgraph: Run selected subgraph (if use_tool) or skip (if reason_only)
    4. Synthesize Response: Generate final answer

    Single-shot execution, no iteration or reflection.
    Can choose reason_only (answer from knowledge) or use_tool (fetch data) based on query context.
    Uses "normal" mode for phase_agent (balanced prompt, not reasoning-biased like thinking mode).
    """

    def __init__(self):
        super().__init__()
        self.graph_name = "NormalGraph"
        self.compiled_graph = self._build_graph()

    @property
    def graph(self) -> CompiledStateGraph:
        return self.compiled_graph

    def default_run_config(self) -> RunConfig:
        return RunConfig(
            graph_name=self.graph_name, recursion_limit=10, timeout_seconds=60
        )

    async def phase_planning_node(self, state: NormalGraphState) -> dict[str, Any]:
        """
        Phase Planning Node - Decide phase title and action type.

        Normal mode provides balanced decision between reason_only and use_tool.
        """
        try:
            resp = await phase_agent.ainvoke(state=state, mode="normal")
            phase_title = resp.get("phase_title", "Research query")
            next_action = resp.get("next_action", "use_tool")

            logger.info(
                f"[NormalGraph] Phase Planning: '{phase_title}', Action={next_action}"
            )

            return {
                "phase_title": phase_title,
                "next_action": next_action,
            }

        except Exception as e:
            logger.error(f"[NormalGraph] Phase Planning failed: {e}")
            return {
                "phase_title": "Research query",
                "next_action": "use_tool",
            }

    async def action_execution_node(self, state: NormalGraphState) -> dict[str, Any]:
        """
        Action Execution Node - Execute the planned action.

        Two paths:
        1. reason_only → Generate reasoning to answer directly
        2. use_tool → Select subgraph and generate query
        """
        conversation = state.get("conversation", [])

        try:
            resp = await action_execution_agent.ainvoke(state=state)
            next_action = state.get("next_action", "use_tool")

            selected_subgraph = resp.get("subgraph", "web_search")
            query = resp.get("query", conversation[-1].content if conversation else "")
            reasoning = resp.get("reasoning", "")

            if next_action == "reason_only":
                logger.info(
                    f"[NormalGraph] Action Execution: Reasoning={reasoning[:100]}..."
                )
            else:
                logger.info(
                    f"[NormalGraph] Action Execution: Tool={selected_subgraph}, Query={query[:100]}..."
                )

            return {
                "selected_subgraph": selected_subgraph,
                "direction": query,
                "reasoning": reasoning,
            }

        except Exception as e:
            logger.error(f"[NormalGraph] Action Execution failed: {e}")
            return {
                "selected_subgraph": "web_search",
                "direction": conversation[-1].content if conversation else "",
                "reasoning": "",
            }

    async def execute_subgraph_node(self, state: NormalGraphState) -> dict[str, Any]:
        """Execute selected subgraph and return documents, or handle reasoning-only mode."""
        subgraph_name = state.get("selected_subgraph")
        next_action = state.get("next_action", "use_tool")

        if next_action == "reason_only":
            logger.info("[NormalGraph] Reasoning-only mode, skipping tool execution")
            return {
                "accumulated_context": state.get("reasoning", ""),
                "response_mode": ResponseMode.REASONING_ONLY,
            }

        if not subgraph_name:
            logger.error("[NormalGraph] No subgraph selected")
            return {"cited_documents": []}

        try:
            subgraph_config = SubgraphRegistry.get_profile(subgraph_name)

            if not subgraph_config:
                logger.error(f"[NormalGraph] Subgraph '{subgraph_name}' not found")
                return {"cited_documents": []}

            exec_ref = subgraph_config.executor
            executor = (
                EXECUTORS.get(exec_ref) if isinstance(exec_ref, str) else exec_ref
            )

            if not executor or not callable(executor):
                logger.error(
                    f"[NormalGraph] Executor for '{subgraph_name}' not callable"
                )
                return {"cited_documents": []}

            logger.info(
                f"[NormalGraph] Executing {subgraph_name}: {state.get('direction')}"
            )

            result_obj: SubgraphOutput = await executor(state)
            main_context = result_obj.main_context or ""
            cited_documents = result_obj.cited_documents or []

            if not main_context and cited_documents:
                main_context = format_context_for_response(cited_documents)

            logger.info(
                f"[NormalGraph] {subgraph_name} returned {len(cited_documents)} documents"
            )

            cited_documents = truncate_docs_by_tokens(
                cited_documents, max_tokens=8192, tokenizer=self.tokenizer
            )
            return {
                "cited_documents": cited_documents,
                "accumulated_context": main_context,
                "response_mode": (
                    ResponseMode.SQL_RESPONSE
                    if state.get("selected_subgraph") == "sql_query"
                    else ResponseMode.STANDARD
                ),
            }

        except Exception as e:
            logger.error(f"[NormalGraph] Error executing {subgraph_name}: {e}")
            return {"cited_documents": []}

    async def synthesize_response_node(self, state: NormalGraphState) -> dict[str, Any]:
        """Synthesize final response using response_agent."""
        response = await response_agent.ainvoke(state)
        resp_metadata = response.response_metadata
        resp_metadata.update(state.get("response_metadata", {}))

        return {
            "final_answer": response.content,
            "response_metadata": resp_metadata,
        }

    def _build_graph(self) -> CompiledStateGraph:
        """
        Build the normal graph workflow.

        Flow: phase_planning → action_execution → execute_subgraph → synthesize_response
        """
        workflow = StateGraph(NormalGraphState)

        workflow.add_node("phase_planning", self.phase_planning_node)
        workflow.add_node("action_execution", self.action_execution_node)
        workflow.add_node("execute_subgraph", self.execute_subgraph_node)
        workflow.add_node("synthesize_response", self.synthesize_response_node)

        workflow.set_entry_point("phase_planning")
        workflow.add_edge("phase_planning", "action_execution")
        workflow.add_edge("action_execution", "execute_subgraph")
        workflow.add_edge("execute_subgraph", "synthesize_response")
        workflow.set_finish_point("synthesize_response")

        return workflow.compile(name=self.graph_name)
