# src/agents/graph/normal_graph.py
"""
Normal Graph - Fast Path for Straightforward Queries
Linear flow: Generate Direction → Execute Subgraph → Synthesize Response
"""

from typing import Any

from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.basic import direction_generation_agent, response_agent
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
    1. Generate Direction: LLM selects subgraph + optimizes query
    2. Execute Subgraph: Run selected subgraph
    3. Synthesize Response: Generate final answer

    Single-shot execution, no iteration.
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

    async def generate_direction_node(self, state: NormalGraphState) -> dict[str, Any]:
        """
        Generate focused research direction for current depth level.
        Similar to ChatGPT's progressive thinking.
        """
        conversation = state.get("conversation", [])
        try:
            resp = await direction_generation_agent.ainvoke(state=state)
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

        logger.info(f"[Direction] {direction}")

        return {
            "direction": direction,
            "action": action,
            "selected_subgraph": selected_subgraph,
            "reasoning": reasoning,
        }

    async def execute_subgraph_node(self, state: NormalGraphState) -> dict[str, Any]:
        """Execute selected subgraph and return documents."""
        subgraph_name = state.get("selected_subgraph")
        if state.get("action") == "reason_only":
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
        """Build the normal graph workflow."""
        workflow = StateGraph(NormalGraphState)

        workflow.add_node("generate_direction", self.generate_direction_node)
        workflow.add_node("execute_subgraph", self.execute_subgraph_node)
        workflow.add_node("synthesize_response", self.synthesize_response_node)

        workflow.set_entry_point("generate_direction")
        workflow.add_edge("generate_direction", "execute_subgraph")
        workflow.add_edge("execute_subgraph", "synthesize_response")
        workflow.set_finish_point("synthesize_response")

        return workflow.compile(name=self.graph_name)
