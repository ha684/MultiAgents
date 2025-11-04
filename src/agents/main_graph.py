# src/agents/main_graph.py
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple
import asyncio

from langchain_core.messages import BaseMessage
from langchain_core.runnables.schema import StreamEvent
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.basic import (
    query_context_agent,
    reflection_agent,
    response_agent,
    router_agent,
)
from src.agents.executors import EXECUTORS
from src.agents.graph.base import GraphAgentBase
from src.agents.shared.manager import execution_manager
from src.agents.shared.registry import SubgraphRegistry, enable_sql, seed_base_subgraphs
from src.agents.tools.server.mcp_retrieve_tools import think
from src.domain.entities.graph import ResponseMode, RunConfig, SubgraphOutput
from src.domain.entities.state import OrchestratorState
from src.domain.schemas.chat import Message, RetrievalContext, TextPart
from src.llm.factory import get_llm
from src.services.conversation_service import ConversationService
from src.utils import format_context_for_response
from src.utils.logger_conf import logger


class OrchestratorGraph(GraphAgentBase[OrchestratorState]):
    """
    Agentic Orchestrator:
    - Supports multi-route decisions from the router and dispatches selected subgraphs concurrently.
    - Aggregates contexts, citations, execution history, and search iterations across parallel runs with fallback handling.
    - Performs iterative reflection and refinement to decide whether to search more, switch strategy, or answer.
    - Normalizes and post-processes agent responses using the response_agent component, supporting multiple output modes.
    """

    MAX_RETRY_ATTEMPTS = 3
    MAX_SEARCH_ITERATIONS = 4

    def __init__(self):
        """Initialize LLMs, conversation service, build the graph, and seed subgraphs."""
        self.llm = get_llm(provider="nxchat")
        self.thinking_llm = self.llm.bind_tools([think])
        self.conv_service = ConversationService()
        self.graph_name = "OrchestratorGraph"
        self.compiled_graph = self._build_graph()
        seed_base_subgraphs()

    @property
    def graph(self) -> CompiledStateGraph:
        """Return the compiled graph."""
        return self.compiled_graph

    def default_run_config(self) -> RunConfig:
        """Return the default run configuration for the orchestrator."""
        return RunConfig(
            graph_name=self.graph_name,
            recursion_limit=100,
            timeout_seconds=600,
        )

    async def contextualize_query_node(
        self, state: OrchestratorState
    ) -> Dict[str, Any]:
        """Normalize the latest user query using conversation history when available."""
        original_query = state["conversation"][-1].content
        if len(state["conversation"]) > 2:
            contextualized = await query_context_agent.ainvoke(
                history=state["conversation"]
            )
            contextualized = contextualized.content
        else:
            contextualized = original_query
        return {"contextualized_query": contextualized}

    async def router_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """Determine one or more subgraph routes based on policy, history, and context."""
        policy = state.get("subgraph_policy", {})
        active_map = SubgraphRegistry.resolve_active(
            allow=policy.get("allow"),
            block=policy.get("block"),
            extras=policy.get("extras"),
        )
        route_decision = await router_agent.ainvoke(state)
        routes = []
        if route_decision is None:
            routes = ["direct_response"]
        elif isinstance(route_decision, dict) and "routes" in route_decision:
            routes = list(route_decision["routes"]) or ["direct_response"]
        elif hasattr(route_decision, "routes"):
            routes = list(route_decision.routes) or ["direct_response"]
        else:
            routes = ["direct_response"]
        resolved = []
        for r in routes:
            cfg = SubgraphRegistry.get_subgraph_active(r, active_map)
            resolved.append(r if cfg or r == "direct_response" else "direct_response")
        routes = [r for r in resolved if r]
        routes = list(dict.fromkeys(routes))
        if not routes:
            routes = ["direct_response"]
        return {"route_decisions": routes}

    def _determine_response_mode_from_result(
        self, state: OrchestratorState, routes: List[str], any_success: bool
    ) -> str:
        """Select response mode from the set of routes and whether any subgraph succeeded."""
        execution_history = state.get("execution_history", [])
        if routes == ["direct_response"]:
            if len(execution_history) >= self.MAX_RETRY_ATTEMPTS:
                return ResponseMode.NO_VIABLE_OPTION
            if len(state["conversation"]) > 2:
                return ResponseMode.FOLLOWUP
            return ResponseMode.CHITCHAT
        if not any_success and len(execution_history) >= self.MAX_RETRY_ATTEMPTS:
            return ResponseMode.NO_VIABLE_OPTION
        if all(r == "sql_query" for r in routes):
            return ResponseMode.SQL_RESPONSE
        if any(r == "deep_research" for r in routes):
            return ResponseMode.ADVANCE
        return ResponseMode.STANDARD

    async def dispatch_subgraph_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """Execute selected subgraphs concurrently, apply fallbacks, and accumulate context."""
        routes = (
            state.get("pending_routes")
            or state.get("route_decisions")
            or ["direct_response"]
        )
        current_iteration = state.get("current_iteration", 1)
        reflection = state.get("reflection_result")
        query_to_use = state.get("contextualized_query", "")
        if reflection and reflection.get("refined_query") and current_iteration > 1:
            query_to_use = reflection["refined_query"]
        if routes == ["direct_response"]:
            response_mode = self._determine_response_mode_from_result(
                state, routes, any_success=False
            )
            return {
                "subgraph_result": "direct_response",
                "response_mode": response_mode,
                "current_iteration": current_iteration,
            }
        policy = state.get("subgraph_policy", {})
        active_map = SubgraphRegistry.resolve_active(
            allow=policy.get("allow"),
            block=policy.get("block"),
            extras=policy.get("extras"),
        )
        execution_history = state.get("execution_history", [])
        if len(execution_history) >= self.MAX_RETRY_ATTEMPTS:
            error_msg = "All retrieval options exhausted after multiple attempts, inform the user."
            return {
                "subgraph_result": "exhausted",
                "subgraph_error": error_msg,
                "response_mode": ResponseMode.NO_VIABLE_OPTION,
                "execution_history": execution_history,
                "route_decisions": ["direct_response"],
                "current_iteration": current_iteration,
            }

        async def run_one(route_name: str) -> Tuple[str, Dict[str, Any]]:
            subgraph_config = SubgraphRegistry.get_subgraph_active(
                route_name, active_map
            )
            exec_ref = subgraph_config.executor if subgraph_config else None
            executor = (
                EXECUTORS.get(exec_ref) if isinstance(exec_ref, str) else exec_ref
            )
            if not executor or not callable(executor):
                return route_name, {
                    "main_context": "",
                    "cited_documents": [],
                    "response_metadata": None,
                    "subgraph_error": f"Executor '{executor}' not found.",
                    "docs_retrieved": 0,
                }
            execution_state = dict(state)
            execution_state["contextualized_query"] = query_to_use
            result_obj: SubgraphOutput = await executor(execution_state)
            main_context = result_obj.main_context or ""
            cited_documents = result_obj.cited_documents or []
            response_metadata = result_obj.response_metadata
            subgraph_error = result_obj.subgraph_error
            if not main_context and cited_documents:
                main_context = format_context_for_response(cited_documents)
            return route_name, {
                "main_context": main_context or "",
                "cited_documents": cited_documents,
                "response_metadata": response_metadata,
                "subgraph_error": subgraph_error,
                "docs_retrieved": len(cited_documents),
            }

        results = await asyncio.gather(*[run_one(r) for r in routes])
        all_cited_docs = (state.get("cited_documents") or []).copy()

        def _content_of(d: Any) -> Optional[str]:
            if hasattr(d, "page_content"):
                return getattr(d, "page_content", None)
            if isinstance(d, dict):
                return d.get("page_content")
            return None

        existing = {c for c in (_content_of(d) for d in all_cited_docs) if c}
        accumulated_context = state.get("accumulated_context", "")
        search_iterations = state.get("search_iterations", [])
        response_metadata_map: Dict[str, Any] = state.get("response_metadata", {}) or {}
        pending_fallbacks: List[str] = []
        any_success = False
        for route_name, data in results:
            main_context = data["main_context"]
            cited_documents = data["cited_documents"]
            subgraph_error = data["subgraph_error"]
            response_metadata_map[route_name] = data["response_metadata"]
            for d in cited_documents:
                c = _content_of(d)
                if c and c not in existing:
                    all_cited_docs.append(d)
                    existing.add(c)
            docs_retrieved = data["docs_retrieved"]
            search_iterations.append(
                {
                    "iteration": current_iteration,
                    "subgraph": route_name,
                    "query": query_to_use,
                    "documents_count": docs_retrieved,
                    "timestamp": datetime.now().isoformat(),
                }
            )
            if main_context:
                if accumulated_context:
                    accumulated_context += (
                        f"\n\n--- Search {current_iteration} ({route_name}) ---\n"
                    )
                accumulated_context += main_context
                any_success = True
            failure_result_condition = (
                subgraph_error and not main_context and docs_retrieved == 0
            )
            if failure_result_condition:
                execution_history.append(
                    {"subgraph": route_name, "error": subgraph_error}
                )
                subgraph_config = SubgraphRegistry.get_subgraph_active(
                    route_name, active_map
                )
                if (
                    subgraph_config
                    and subgraph_config.fallback_chain
                    and len(execution_history) < self.MAX_RETRY_ATTEMPTS
                ):
                    tried_routes = {h["subgraph"] for h in execution_history}
                    available_fallbacks = [
                        fb
                        for fb in subgraph_config.fallback_chain
                        if fb not in tried_routes
                    ]
                    if available_fallbacks:
                        pending_fallbacks.append(available_fallbacks[0])
        response_mode = self._determine_response_mode_from_result(
            state, routes, any_success
        )
        if pending_fallbacks:
            return {
                "subgraph_result": "retry_fallback",
                "execution_history": execution_history,
                "route_decisions": routes,
                "pending_routes": pending_fallbacks,
                "main_context": None,
                "cited_documents": all_cited_docs,
                "subgraph_error": None,
                "search_iterations": search_iterations,
                "accumulated_context": accumulated_context,
                "current_iteration": current_iteration + 1,
                "response_metadata": response_metadata_map,
                "response_mode": response_mode,
            }
        if not any_success and routes != ["direct_response"]:
            return {
                "subgraph_result": "retry_router",
                "execution_history": execution_history,
                "response_mode": ResponseMode.STANDARD,
                "search_iterations": search_iterations,
                "accumulated_context": accumulated_context,
                "cited_documents": all_cited_docs,
                "current_iteration": current_iteration + 1,
                "subgraph_error": "No successful results; retrying router.",
                "response_metadata": response_metadata_map,
            }
        return {
            "main_context": accumulated_context,
            "cited_documents": all_cited_docs,
            "response_metadata": response_metadata_map,
            "subgraph_error": None,
            "subgraph_result": "success",
            "response_mode": response_mode,
            "execution_history": execution_history,
            "search_iterations": search_iterations,
            "accumulated_context": accumulated_context,
            "current_iteration": current_iteration + 1,
            "pending_routes": [],
        }

    async def reflection_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """Reflect on current aggregated results to decide the next step."""
        routes = state.get("route_decisions", [])

        if routes and all(r in ["direct_response"] for r in routes):
            return {
                "reflection_result": {
                    "is_sufficient": True,
                    "missing_aspects": [],
                    "reasoning": f"No reflection needed for {', '.join(routes)}",
                    "suggested_next_action": "respond",
                    "refined_query": None,
                }
            }
        reflection_result = await reflection_agent.ainvoke(state)
        if not reflection_result:
            reflection_result = {
                "is_sufficient": True,
                "missing_aspects": [],
                "reasoning": "Failed to get reflection, proceeding to respond",
                "suggested_next_action": "respond",
                "refined_query": None,
            }
        return {"reflection_result": reflection_result}

    def route_after_reflection(self, state: OrchestratorState) -> str:
        """Choose the next step after reflection."""
        reflection = state.get("reflection_result")
        if not reflection:
            return "final_response"
        action = reflection.get("suggested_next_action", "respond")
        current_iteration = state.get("current_iteration", 1)
        max_iterations = state.get("max_iterations", self.MAX_SEARCH_ITERATIONS)
        if current_iteration >= max_iterations:
            return "final_response"
        if action == "respond" or reflection.get("is_sufficient"):
            return "final_response"
        elif action == "search_more":
            return "dispatch_subgraph"
        elif action == "switch_strategy":
            return "router"
        else:
            return "final_response"

    def route_after_dispatch(self, state: OrchestratorState) -> str:
        """Decide the next node after concurrent dispatch."""
        if state.get("pending_routes"):
            return "dispatch_subgraph"
        result = state.get("subgraph_result", "success")
        if result == "retry_router":
            return "router"
        return "reflection"

    async def final_response_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """Produce the final response from aggregated context and metadata."""
        routes = state.get("route_decisions", [])
        response_mode = state.get("response_mode", ResponseMode.STANDARD)
        search_iterations = state.get("search_iterations", [])
        num_iterations = len(search_iterations)
        response = await response_agent.ainvoke(state)
        response_metadata = state.get("response_metadata", {})
        response_metadata.update(
            {
                "routes": routes,
                "response_mode": response_mode,
                "execution_history": state.get("execution_history", []),
                "search_iterations": num_iterations,
                "reflection_used": state.get("reflection_result") is not None,
            }
        )
        return {
            "final_answer": response.content,
            "response_metadata": response_metadata,
        }

    def _build_graph(self) -> CompiledStateGraph:
        """Assemble the orchestration workflow with multi-route concurrent dispatch."""
        workflow = StateGraph(OrchestratorState)
        workflow.add_node("contextualize_query", self.contextualize_query_node)
        workflow.add_node("router", self.router_node)
        workflow.add_node("dispatch_subgraph", self.dispatch_subgraph_node)
        workflow.add_node("reflection", self.reflection_node)
        workflow.add_node("final_response", self.final_response_node)
        workflow.set_entry_point("contextualize_query")
        workflow.add_edge("contextualize_query", "router")
        workflow.add_edge("router", "dispatch_subgraph")
        workflow.add_conditional_edges(
            "dispatch_subgraph",
            self.route_after_dispatch,
            {
                "router": "router",
                "reflection": "reflection",
                "dispatch_subgraph": "dispatch_subgraph",
            },
        )
        workflow.add_conditional_edges(
            "reflection",
            self.route_after_reflection,
            {
                "router": "router",
                "dispatch_subgraph": "dispatch_subgraph",
                "final_response": "final_response",
            },
        )
        workflow.set_finish_point("final_response")
        return workflow.compile(name=self.graph_name)

    async def astream(
        self, conversation: List[BaseMessage]
    ) -> AsyncGenerator[StreamEvent, None]:
        """Run the orchestrator on the entire conversation."""
        meta = conversation[-1].additional_kwargs or {}
        conversation_id = meta.get("conversation_id")
        db_url = meta.get("db_url")
        allow_tables = meta.get("allow_tables", [])

        allow = meta.get("enabled_subgraphs")
        block = meta.get("disabled_subgraphs")

        extras = {}
        if db_url and allow_tables:
            extras["sql_query"] = enable_sql(db_url, allow_tables)

        subgraph_policy = {
            "allow": allow or None,
            "block": block or [],
            "extras": extras,
        }

        initial_state = OrchestratorState(
            conversation=conversation,
            subgraph_policy=subgraph_policy,
            search_iterations=[],
            current_iteration=1,
            max_iterations=self.MAX_SEARCH_ITERATIONS,
            accumulated_context="",
            reflection_result=None,
        )

        conversation_id = conversation[-1].additional_kwargs.get("conversation_id")
        execution_manager.start_execution(conversation_id)
        try:
            async for event in super().astream(initial_state):
                yield event
        finally:
            execution_manager.finish_execution(conversation_id)

    async def ainvoke(
        self, conversation: List[BaseMessage]
    ) -> Optional[Dict[str, Any]]:
        """Non-streaming execution (backward compatible)"""
        try:
            initial_state = OrchestratorState(
                conversation=conversation,
                search_iterations=[],
                current_iteration=1,
                max_iterations=self.MAX_SEARCH_ITERATIONS,
                accumulated_context="",
                reflection_result=None,
            )
            final_result = await super().ainvoke(initial_state)
            message = Message(
                parts=[
                    TextPart(type="text", text=final_result.get("final_answer", ""))
                ],
                role="agent",
                metadata=final_result.get("response_metadata", {}),
                retrieval_context=RetrievalContext(
                    **final_result.get("retrieval_contexts", {})
                ),
            )
            return message
        except Exception as e:
            logger.error(f"Error running orchestrator graph: {e}")
            raise e
