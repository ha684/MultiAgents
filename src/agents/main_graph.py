# src/agents/main_graph.py
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional, Set, Tuple
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
            cfg = SubgraphRegistry.get_profile(r)
            resolved.append(r if cfg or r == "direct_response" else "direct_response")
        routes = [r for r in resolved if r]
        routes = list(dict.fromkeys(routes))

        failed = state.get("failed_subgraphs", set())
        routes = [r for r in routes if r not in failed] or ["direct_response"]

        return {"route_decisions": routes}

    def _determine_response_mode_from_result(
        self,
        state: OrchestratorState,
        routes: List[str],
        subgraph_results: Dict[str, Dict[str, Any]],
    ) -> str:
        """Select response mode from the set of routes and whether any subgraph succeeded."""
        execution_history = state.get("execution_history", [])
        if routes == ["direct_response"]:
            if len(execution_history) >= self.MAX_RETRY_ATTEMPTS:
                return ResponseMode.NO_VIABLE_OPTION
            if len(state["conversation"]) > 2:
                return ResponseMode.FOLLOWUP
            return ResponseMode.CHITCHAT
        if (
            any(r.get("status") == "error" for r in subgraph_results.values())
            and len(execution_history) >= self.MAX_RETRY_ATTEMPTS
        ):
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

        subgraph_results: Dict[str, Dict[str, Any]] = state.get("subgraph_results", {})
        failed_subgraphs: Set[str] = state.get("failed_subgraphs", set())

        seen_urls: Set[str] = set(state.get("seen_urls", set()))
        seen_doc_ids: Set[str] = set(state.get("seen_doc_ids", set()))

        if reflection and reflection.get("refined_query") and current_iteration > 1:
            query_to_use = reflection["refined_query"]

        if routes == ["direct_response"]:
            response_mode = self._determine_response_mode_from_result(
                state, routes, subgraph_results
            )
            return {
                "subgraph_result": "direct_response",
                "response_mode": response_mode,
                "current_iteration": current_iteration,
            }
        execution_history = state.get("execution_history", [])

        routes_to_execute = [r for r in routes if r not in failed_subgraphs]

        if not routes_to_execute:
            error_msg = "All subgraphs have failed, no viable options remaining."
            return {
                "subgraph_result": "exhausted",
                "subgraph_error": error_msg,
                "response_mode": ResponseMode.NO_VIABLE_OPTION,
                "execution_history": execution_history,
                "route_decisions": ["direct_response"],
                "current_iteration": current_iteration,
                "subgraph_results": subgraph_results,
                "failed_subgraphs": failed_subgraphs,
            }

        async def run_one(route_name: str) -> Tuple[str, Dict[str, Any]]:
            try:
                subgraph_config = SubgraphRegistry.get_profile(route_name)
                exec_ref = subgraph_config.executor if subgraph_config else None
                executor = (
                    EXECUTORS.get(exec_ref) if isinstance(exec_ref, str) else exec_ref
                )
                if not executor or not callable(executor):
                    return route_name, {
                        "status": "error",
                        "main_context": "",
                        "cited_documents": [],
                        "response_metadata": None,
                        "subgraph_error": f"Executor '{executor}' not found.",
                    }

                execution_state = dict(state)
                execution_state["contextualized_query"] = query_to_use
                execution_state["seen_urls"] = seen_urls
                execution_state["seen_doc_ids"] = seen_doc_ids
                execution_state["duplicate_skip_ratio"] = state.get(
                    "duplicate_skip_ratio", 0.7
                )

                result_obj: SubgraphOutput = await executor(execution_state)

                main_context = result_obj.main_context or ""
                cited_documents = result_obj.cited_documents or []
                response_metadata = result_obj.response_metadata
                subgraph_error = result_obj.subgraph_error or ""

                if not main_context and cited_documents:
                    main_context = format_context_for_response(cited_documents)

                status = (
                    "error"
                    if subgraph_error
                    else ("success" if (main_context or cited_documents) else "empty")
                )

                return route_name, {
                    "status": status,
                    "main_context": main_context,
                    "cited_documents": cited_documents,
                    "response_metadata": response_metadata,
                    "subgraph_error": subgraph_error or None,
                }

            except Exception as e:
                return route_name, {
                    "status": "error",
                    "main_context": "",
                    "cited_documents": [],
                    "response_metadata": {"exception": f"{type(e).__name__}: {e}"},
                    "subgraph_error": f"{type(e).__name__}: {e}",
                }

        results = await asyncio.gather(*[run_one(r) for r in routes_to_execute])

        def _doc_key(d: Any) -> Optional[str]:
            meta = getattr(d, "metadata", {}) or {}
            return (
                meta.get("document_id")
                or meta.get("original_filename")
                or (
                    getattr(d, "page_content", None)
                    if hasattr(d, "page_content")
                    else (d.get("page_content") if isinstance(d, dict) else None)
                )
            )

        all_cited_docs = (state.get("cited_documents") or []).copy()
        existing_keys = {k for k in (_doc_key(doc) for doc in all_cited_docs) if k}

        accumulated_context = state.get("accumulated_context", "")
        search_iterations = state.get("search_iterations", [])
        response_metadata_map: Dict[str, Any] = state.get("response_metadata", {}) or {}

        any_early_terminate = False
        highest_dup_ratio = 0.0

        for route_name, data in results:
            status = data.get("status", "error")
            main_context = data["main_context"]
            cited_documents = data["cited_documents"]
            subgraph_error = data["subgraph_error"]
            resp_meta = data["response_metadata"] or {}

            subgraph_results[route_name] = {
                "status": status,
                "main_context": main_context,
                "error": subgraph_error,
                "iteration": current_iteration,
            }
            response_metadata_map[route_name] = resp_meta

            new_urls = set(resp_meta.get("new_urls", []))
            new_doc_ids = set(resp_meta.get("new_doc_ids", []))
            seen_urls |= new_urls
            seen_doc_ids |= new_doc_ids

            if resp_meta.get("early_terminate"):
                any_early_terminate = True
                highest_dup_ratio = max(
                    highest_dup_ratio, float(resp_meta.get("duplicate_ratio", 0.0))
                )

            for d in cited_documents:
                k = _doc_key(d)
                if k and k not in existing_keys:
                    all_cited_docs.append(d)
                    existing_keys.add(k)

            search_iterations.append(
                {
                    "iteration": current_iteration,
                    "subgraph": route_name,
                    "query": query_to_use,
                    "status": status,
                    "timestamp": datetime.now().isoformat(),
                    "duplicate_ratio": resp_meta.get("duplicate_ratio"),
                    "early_terminate": resp_meta.get("early_terminate", False),
                }
            )

            if main_context:
                if accumulated_context:
                    accumulated_context += (
                        f"\n\n--- Search {current_iteration} ({route_name}) ---\n"
                    )
                accumulated_context += main_context
                execution_history.append(
                    {
                        "subgraph": route_name,
                        "error": "subgraph succeeded",
                        "iteration": current_iteration,
                    }
                )

            if status == "error":
                failed_subgraphs.add(route_name)
                execution_history.append(
                    {
                        "subgraph": route_name,
                        "error": subgraph_error,
                        "iteration": current_iteration,
                    }
                )

        response_mode = self._determine_response_mode_from_result(
            state, routes, subgraph_results
        )

        logger.info(f"Accumulated context: {accumulated_context}")
        had_error = any(data.get("status") == "error" for _, data in results)
        had_success = any(data.get("status") == "success" for _, data in results)

        if had_error and not had_success and routes != ["direct_response"]:
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
                "subgraph_results": subgraph_results,
                "failed_subgraphs": failed_subgraphs,
                "seen_urls": seen_urls,
                "seen_doc_ids": seen_doc_ids,
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
            "subgraph_results": subgraph_results,
            "failed_subgraphs": failed_subgraphs,
            "seen_urls": seen_urls,
            "seen_doc_ids": seen_doc_ids,
            "duplication_high": any_early_terminate,
        }

    async def reflection_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """Reflect on current aggregated results to decide the next step."""
        routes = state.get("route_decisions", [])

        duplication_high = state.get("duplication_high")

        last_iteration_num = state.get("current_iteration", 2) - 1
        subgraph_results = state.get("subgraph_results", {})

        failed_in_last_iteration = False
        for route, result in subgraph_results.items():
            if (
                result.get("iteration") == last_iteration_num
                and result.get("status") == "error"
            ):
                failed_in_last_iteration = True
                break

        if duplication_high and not failed_in_last_iteration:
            return {
                "reflection_result": {
                    "is_sufficient": True,
                    "missing_aspects": [],
                    "reasoning": "High duplication detected and no subgraphs failed. Responding.",
                    "suggested_next_action": "respond",
                    "refined_query": None,
                    "subgraphs_to_retry": [],
                }
            }

        if routes and all(r in ["direct_response"] for r in routes):
            return {
                "reflection_result": {
                    "is_sufficient": True,
                    "missing_aspects": [],
                    "reasoning": f"No reflection needed for {', '.join(routes)}",
                    "suggested_next_action": "respond",
                    "refined_query": None,
                    "subgraphs_to_retry": [],
                }
            }

        if routes and all(r in ["direct_response"] for r in routes):
            return {
                "reflection_result": {
                    "is_sufficient": True,
                    "missing_aspects": [],
                    "reasoning": f"No reflection needed for {', '.join(routes)}",
                    "suggested_next_action": "respond",
                    "refined_query": None,
                    "subgraphs_to_retry": [],
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
                "subgraphs_to_retry": [],
            }

        updates = {"reflection_result": reflection_result}
        if reflection_result.get("suggested_next_action") == "search_more":
            subgraphs_to_retry = reflection_result.get("subgraphs_to_retry", [])
            failed_subgraphs = state.get("failed_subgraphs", set())
            valid_retries = [s for s in subgraphs_to_retry if s not in failed_subgraphs]
            if valid_retries:
                updates["pending_routes"] = valid_retries

        return updates

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
            if state.get("pending_routes"):
                return "dispatch_subgraph"
            return "final_response"
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
        subgraph_results = state.get("subgraph_results", {})

        response = await response_agent.ainvoke(state)
        response_metadata = state.get("response_metadata", {})
        response_metadata.update(
            {
                "routes": routes,
                "response_mode": response_mode,
                "execution_history": state.get("execution_history", []),
                "search_iterations": num_iterations,
                "reflection_used": state.get("reflection_result") is not None,
                "subgraph_results": subgraph_results,
                "failed_subgraphs": list(state.get("failed_subgraphs", set())),
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

        allow = meta.get("enabled_subgraphs", [])
        block = meta.get("disabled_subgraphs", [])

        extras = {}
        if db_url and allow_tables:
            extras["sql_query"] = enable_sql(db_url, allow_tables)
        else:
            block.append("sql_query")

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
