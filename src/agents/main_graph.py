# src/agents/main_graph.py
import textwrap
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
    get_buffer_string,
)
from langchain_core.runnables.schema import StreamEvent
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.basic import query_context_agent, response_agent
from src.agents.executors import EXECUTORS
from src.agents.graph.base import GraphAgentBase
from src.agents.graph.schemas import RouteDecision
from src.agents.graph.state import OrchestratorState, ReflectionResult, SearchIteration
from src.agents.shared.manager import execution_manager
from src.agents.shared.prompts import PromptTemplates
from src.agents.shared.registry import SubgraphRegistry, enable_sql, seed_base_subgraphs
from src.agents.tools.server.mcp_retrieve_tools import think
from src.domain.entities.graph import ResponseMode, RunConfig, SubgraphOutput
from src.domain.schemas.chat import Message, RetrievalContext, TextPart
from src.llm.factory import get_llm
from src.services.conversation_service import ConversationService
from src.utils import format_context_for_response, parse_response
from src.utils.logger_conf import logger


class OrchestratorGraph(GraphAgentBase[OrchestratorState]):
    """
    Agentic Orchestrator:
    - Dynamically routes and dispatches user queries to the appropriate subgraph based on a centralized registry of active modules.
    - Coordinates multi-step search and retrieval workflows, supporting fallback strategies to handle cases where initial attempts are insufficient or fail.
    - Performs iterative reflection and refinement of queries, applying reasoning steps to assess information sufficiency and optimize subsequent search iterations.
    - Normalizes and post-processes agent responses using the response_agent component, supporting multiple output modes for tailored, high-quality answers.
    """

    MAX_RETRY_ATTEMPTS = 3
    MAX_SEARCH_ITERATIONS = 4

    def __init__(self):
        """Khởi tạo LLM, dịch vụ hội thoại, build graph và seed subgraphs."""
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
        """Return the default run config for the orchestrator."""
        return RunConfig(
            graph_name=self.graph_name,
            recursion_limit=100,
            timeout_seconds=600,
        )

    async def confirmation_gate_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """
        If the previous message is a confirmation prompt and the user has just responded:
        - Approve → force route to pending_route, skip contextualize/router.
        - Reject  → block pending_route then return to normal flow.
        """
        pending = extract_pending_route_from_prev_assistant(state)
        if not pending:
            return {"gate": "contextualize_query"}

        if is_user_rejected_research(state):
            policy = state.get("subgraph_policy", {}) or {}
            blocked = set(policy.get("block", []))
            blocked.add(pending)
            policy["block"] = list(blocked)
            return {
                "subgraph_policy": policy,
                "gate": "contextualize_query",
            }

        return {"gate": "contextualize_query"}

    def route_after_gate(self, state: OrchestratorState) -> str:
        return state.get("gate", "contextualize_query")

    async def contextualize_query_node(
        self, state: OrchestratorState
    ) -> Dict[str, Any]:
        """Normalize the query based on the conversation history."""
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
        """Determine the route subgraph dynamically based on policy, history and context."""
        max_iterations = 3
        conversation = state["conversation"]

        policy = state.get("subgraph_policy", {})
        active_map = SubgraphRegistry.resolve_active(
            allow=policy.get("allow"),
            block=policy.get("block"),
            extras=policy.get("extras"),
        )
        state["active_subgraphs"] = list(active_map.keys())
        subgraph_definitions = SubgraphRegistry.definitions_from_map(active_map)

        execution_history = state.get("execution_history", [])

        subgraph_context = "\n\n".join(
            [
                f"**{tool['name']}**:\n{tool['description']}"
                for tool in subgraph_definitions
            ]
        )

        history_context = ""
        if execution_history:
            history_context = "\n\n**Previous attempts:**\n" + "\n".join(
                [
                    f"- {h['subgraph']}: {h.get('error', 'No result')}"
                    for h in execution_history
                ]
            )

        conversation_context = get_buffer_string(conversation)

        system_prompt = SystemMessage(content=PromptTemplates.ROUTER_PROMPT)
        context_message = HumanMessage(
            content=textwrap.dedent(
                f"""<available_subgraphs>
                {subgraph_context}
                </available_subgraphs>

                <execution_history>
                {history_context if history_context else "No previous attempts"}
                </execution_history>

                <conversation_context>
                {conversation_context if conversation_context else "No previous conversation"}
                </conversation_context>

                <current_query>
                {conversation[-1].content}
                </current_query>

                Analyze the query and select the most appropriate subgraph route.
                """
            )
        )
        messages: List[BaseMessage] = [system_prompt, context_message]

        router_llm = self.thinking_llm
        response = await self.iterative_llm_call_structured(
            messages=messages,
            llm_with_tools=router_llm,
            available_tools={"think": think},
            max_iterations=max_iterations,
            parse_fn=parse_route_decision,
            retry_prompt=(
                "Please provide the route decision in correct JSON format with 'route' key "
                "matching one of the available subgraph names."
            ),
        )

        if not response:
            return {"route_decision": "direct_response"}

        route = response["route"]
        subgraph_config = SubgraphRegistry.get_subgraph_active(route, active_map)

        if not subgraph_config:
            route = "direct_response"

        if subgraph_config and subgraph_config.requires_confirmation:
            if not _is_user_approved_research(state):
                return {"route_decision": route, "needs_confirmation": True}

        return {"route_decision": route, "needs_confirmation": False}

    def _determine_response_mode_from_result(
        self, state: OrchestratorState, route: str, result: Dict[str, Any]
    ) -> str:
        """Determine the response mode after running the subgraph."""
        execution_history = state.get("execution_history", [])

        if state.get("needs_confirmation", False):
            return ResponseMode.CONFIRMATION_REQUIRED

        if (
            result.get("subgraph_error")
            and not result.get("main_context")
            and not result.get("cited_documents")
        ):
            return ResponseMode.ERROR

        if route == "sql_query":
            return ResponseMode.SQL_RESPONSE

        if route == "direct_response":
            if len(execution_history) >= self.MAX_RETRY_ATTEMPTS:
                return ResponseMode.NO_VIABLE_OPTION
            if len(state["conversation"]) > 2:
                return ResponseMode.FOLLOWUP
            return ResponseMode.CHITCHAT

        if route == "deep_research":
            return ResponseMode.ADVANCE

        return ResponseMode.STANDARD

    async def dispatch_subgraph_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """Execute the selected subgraph, manage retry/fallback and accumulate context."""
        route = state["route_decision"]
        current_iteration = state.get("current_iteration", 1)
        reflection = state.get("reflection_result")
        query_to_use = state.get("contextualized_query", "")

        if reflection and reflection.get("refined_query") and current_iteration > 1:
            query_to_use = reflection["refined_query"]

        if state.get("needs_confirmation", False):
            response_mode = self._determine_response_mode_from_result(state, route, {})
            return {
                "subgraph_result": "needs_confirmation",
                "response_mode": response_mode,
            }

        if route == "direct_response":
            response_mode = self._determine_response_mode_from_result(state, route, {})
            return {
                "subgraph_result": "direct_response",
                "response_mode": response_mode,
            }

        policy = state.get("subgraph_policy", {})
        active_map = SubgraphRegistry.resolve_active(
            allow=policy.get("allow"),
            block=policy.get("block"),
            extras=policy.get("extras"),
        )
        subgraph_config = SubgraphRegistry.get_subgraph_active(route, active_map)

        if subgraph_config and getattr(subgraph_config, "requires_confirmation", False):
            if not _is_user_approved_research(state):
                return {
                    "subgraph_result": "needs_confirmation",
                    "response_mode": ResponseMode.CONFIRMATION_REQUIRED,
                    "needs_confirmation": True,
                    "route_decision": route,
                }

        exec_ref = subgraph_config.executor if subgraph_config else None
        executor = EXECUTORS.get(exec_ref) if isinstance(exec_ref, str) else exec_ref

        if not executor or not callable(executor):
            error_msg = f"Executor '{executor}' not found."
            return {
                "subgraph_result": "error",
                "subgraph_error": error_msg,
                "response_mode": ResponseMode.ERROR,
            }

        execution_history = state.get("execution_history", [])
        if len(execution_history) >= self.MAX_RETRY_ATTEMPTS:
            error_msg = "All retrieval options exhausted after multiple attempts, inform the user about that."
            return {
                "subgraph_result": "exhausted",
                "subgraph_error": error_msg,
                "response_mode": ResponseMode.NO_VIABLE_OPTION,
                "execution_history": execution_history,
                "route_decision": "direct_response",
            }

        # Execute
        execution_state = dict(state)
        execution_state["contextualized_query"] = query_to_use
        result_obj: SubgraphOutput = await executor(execution_state)

        main_context = result_obj.main_context or ""
        cited_documents = result_obj.cited_documents or []
        response_metadata = result_obj.response_metadata
        subgraph_error = result_obj.subgraph_error

        if not main_context and cited_documents:
            try:
                main_context = format_context_for_response(cited_documents)
            except Exception:
                main_context = ""

        all_cited_docs = (state.get("cited_documents") or []).copy()

        def _content_of(d: Any) -> Optional[str]:
            if hasattr(d, "page_content"):
                return getattr(d, "page_content", None)
            if isinstance(d, dict):
                return d.get("page_content")
            return None

        existing = {c for c in (_content_of(d) for d in all_cited_docs) if c}
        new_docs: List[Any] = cited_documents
        for d in new_docs:
            c = _content_of(d)
            if c and c not in existing:
                all_cited_docs.append(d)
                existing.add(c)

        docs_retrieved = len(new_docs)
        search_iterations = state.get("search_iterations", [])
        result_summary = (
            main_context
            if main_context
            else (
                f"{docs_retrieved} documents retrieved"
                if docs_retrieved > 0
                else "No results"
            )
        )

        search_iteration: SearchIteration = {
            "iteration": current_iteration,
            "subgraph": route,
            "query": query_to_use,
            "result_summary": result_summary,
            "documents_count": docs_retrieved,
            "timestamp": datetime.now().isoformat(),
        }
        search_iterations.append(search_iteration)

        accumulated_context = state.get("accumulated_context", "")
        if main_context:
            if accumulated_context:
                accumulated_context += (
                    f"\n\n--- Search {current_iteration} ({route}) ---\n"
                )
            accumulated_context += main_context

        failure_result_condition = (
            subgraph_error and not main_context and docs_retrieved == 0
        )

        if failure_result_condition:
            execution_history.append({"subgraph": route, "error": subgraph_error})

            if (
                subgraph_config.fallback_chain
                and len(execution_history) < self.MAX_RETRY_ATTEMPTS
            ):
                tried_routes = {h["subgraph"] for h in execution_history}
                available_fallbacks = [
                    fb
                    for fb in subgraph_config.fallback_chain
                    if fb not in tried_routes
                ]
                if available_fallbacks:
                    next_fallback = available_fallbacks[0]

                    # Check if the fallback requires confirmation
                    next_cfg = SubgraphRegistry.get_subgraph_active(
                        next_fallback, active_map
                    )
                    needs_conf = (
                        next_cfg
                        and getattr(next_cfg, "requires_confirmation", False)
                        and not _is_user_approved_research(state)
                    )

                    if needs_conf:
                        # Short-circuit: DO NOT execute fallback, ask for confirmation
                        response_mode = self._determine_response_mode_from_result(
                            state, next_fallback, {}
                        )
                        return {
                            "subgraph_result": "needs_confirmation",
                            "execution_history": execution_history,
                            "route_decision": next_fallback,
                            "fallback_source": route,
                            "needs_confirmation": True,
                            "response_mode": response_mode,
                            "main_context": None,
                            "cited_documents": all_cited_docs,
                            "subgraph_error": None,
                            "search_iterations": search_iterations,
                            "accumulated_context": accumulated_context,
                            # Do not increase iteration because the new round has not been executed
                            "current_iteration": current_iteration,
                            "response_metadata": response_metadata,
                        }

                    # normal fallback: change route and allow execution in the next round
                    response_mode = self._determine_response_mode_from_result(
                        state, next_fallback, {}
                    )
                    return {
                        "subgraph_result": "retry_fallback",
                        "execution_history": execution_history,
                        "route_decision": next_fallback,
                        "fallback_source": route,
                        "main_context": None,
                        "cited_documents": all_cited_docs,
                        "subgraph_error": None,
                        "search_iterations": search_iterations,
                        "accumulated_context": accumulated_context,
                        "current_iteration": current_iteration + 1,
                        "response_metadata": response_metadata,
                    }

            # No fallback left or exceeded retry limit -> return router to choose a different strategy
            return {
                "subgraph_result": "retry_router",
                "execution_history": execution_history,
                "response_mode": ResponseMode.STANDARD,
                "search_iterations": search_iterations,
                "accumulated_context": accumulated_context,
                "cited_documents": all_cited_docs,
                "current_iteration": current_iteration + 1,
                "subgraph_error": subgraph_error,
                "response_metadata": response_metadata,
            }

        # Success
        response_mode = self._determine_response_mode_from_result(
            state,
            route,
            {
                "main_context": main_context,
                "cited_documents": all_cited_docs,
                "subgraph_error": subgraph_error,
            },
        )
        return {
            "main_context": main_context,
            "cited_documents": all_cited_docs,
            "response_metadata": response_metadata,
            "subgraph_error": subgraph_error,
            "subgraph_result": "success",
            "response_mode": response_mode,
            "execution_history": execution_history,
            "search_iterations": search_iterations,
            "accumulated_context": accumulated_context,
            "current_iteration": current_iteration + 1,
        }

    async def reflection_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """Reflect on the current result to decide the next step."""
        current_iteration = state.get("current_iteration", 1)
        max_iterations = state.get("max_iterations", self.MAX_SEARCH_ITERATIONS)
        route = state.get("route_decision")

        if route in ["direct_response", "sql_query"] or state.get("needs_confirmation"):
            return {
                "reflection_result": {
                    "is_sufficient": True,
                    "missing_aspects": [],
                    "reasoning": f"No reflection needed for {route}",
                    "suggested_next_action": "respond",
                    "refined_query": None,
                }
            }

        search_iterations = state.get("search_iterations", [])
        search_history_text = (
            "\n".join(
                [
                    f"Iteration {it['iteration']}: {it['subgraph']} - Query: '{it['query']}' - {it['result_summary']}"
                    for it in search_iterations
                ]
            )
            if search_iterations
            else "No previous searches"
        )

        latest_iteration = search_iterations[-1] if search_iterations else None
        latest_subgraph = latest_iteration["subgraph"] if latest_iteration else route
        latest_query = (
            latest_iteration["query"]
            if latest_iteration
            else state.get("contextualized_query", "")
        )
        agg_docs = len(state.get("cited_documents") or [])
        last_docs = latest_iteration["documents_count"] if latest_iteration else 0
        docs_count = max(agg_docs, last_docs)
        result_summary = (
            latest_iteration["result_summary"] if latest_iteration else "Just completed"
        )

        accumulated_context = state.get("accumulated_context", "")
        if not accumulated_context:
            if state.get("main_context"):
                accumulated_context = state.get("main_context", "")
            elif agg_docs > 0:
                try:
                    accumulated_context = format_context_for_response(
                        state.get("cited_documents") or []
                    )
                except Exception:
                    accumulated_context = ""

        system_prompt = SystemMessage(
            content=PromptTemplates.ORCHESTRATOR_REFLECTION_PROMPT
        )
        human_prompt = HumanMessage(
            content=PromptTemplates.ORCHESTRATOR_REFLECTION_HUMAN_PROMPT.format(
                user_query=state["conversation"][-1].content,
                current_iteration=current_iteration,
                max_iterations=max_iterations,
                search_history=search_history_text,
                accumulated_context=accumulated_context
                if accumulated_context
                else "No information gathered yet",
                latest_subgraph=latest_subgraph,
                latest_query=latest_query,
                docs_count=docs_count,
                result_summary=result_summary,
            )
        )
        messages: List[BaseMessage] = [system_prompt, human_prompt]

        reflection_result = await self.iterative_llm_call_structured(
            messages=messages,
            llm_with_tools=self.thinking_llm,
            available_tools={"think": think},
            max_iterations=3,
            parse_fn=parse_reflection_result,
            retry_prompt=(
                "Please provide the reflection result in correct JSON format with all required fields."
            ),
        )

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
        """Decide the next step after reflection."""
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
        """Decide the next node after dispatching the subgraph."""
        result = state.get("subgraph_result", "success")
        if result == "retry_fallback":
            return "dispatch_subgraph"
        elif result == "retry_router":
            return "router"
        elif result == "needs_confirmation":
            return "reflection"
        else:
            return "reflection"

    async def final_response_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """Create the final response based on the mode and accumulated context."""
        route = state.get("route_decision")
        response_mode = state.get("response_mode", ResponseMode.STANDARD)
        search_iterations = state.get("search_iterations", [])
        num_iterations = len(search_iterations)

        knowledge_context = state.get("accumulated_context", "") or state.get(
            "main_context", ""
        )
        pending_route = (
            route if response_mode == ResponseMode.CONFIRMATION_REQUIRED else None
        )

        response = await response_agent.ainvoke(
            contexts=state.get("cited_documents", []),
            history=state["conversation"],
            mode=response_mode,
            accumulated_knowledge=knowledge_context,
            execution_history=state.get("execution_history", []),
            error_message=state.get("subgraph_error"),
            pending_route=pending_route,
        )

        response_metadata = state.get("response_metadata", {})
        response_metadata.update(
            {
                "route": route,
                "response_mode": response_mode,
                "execution_history": state.get("execution_history", []),
                "search_iterations": num_iterations,
                "reflection_used": state.get("reflection_result") is not None,
                "pending_route": pending_route,
            }
        )

        return {
            "final_answer": response.content,
            "response_metadata": response_metadata,
        }

    def _build_graph(self) -> CompiledStateGraph:
        """Build the graph from top to bottom."""
        workflow = StateGraph(OrchestratorState)

        workflow.add_node("confirmation_gate", self.confirmation_gate_node)
        workflow.add_node("contextualize_query", self.contextualize_query_node)
        workflow.add_node("router", self.router_node)
        workflow.add_node("dispatch_subgraph", self.dispatch_subgraph_node)
        workflow.add_node("reflection", self.reflection_node)
        workflow.add_node("final_response", self.final_response_node)

        workflow.set_entry_point("confirmation_gate")

        workflow.add_conditional_edges(
            "confirmation_gate",
            self.route_after_gate,
            {
                "dispatch_subgraph": "dispatch_subgraph",
                "contextualize_query": "contextualize_query",
            },
        )

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


def parse_route_decision(content: str) -> Optional[RouteDecision]:
    """Parse route decision from content"""
    try:
        parsed = parse_response(content)
        if parsed is None:
            return None
        return parsed
    except Exception as e:
        logger.error(f"Error parsing route decision: {e}")
        return None


def parse_reflection_result(content: str) -> Optional[ReflectionResult]:
    """Parse reflection result from content"""
    try:
        parsed = parse_response(content)
        if parsed is None:
            return None

        required_fields = [
            "is_sufficient",
            "missing_aspects",
            "reasoning",
            "suggested_next_action",
            "refined_query",
        ]
        for field in required_fields:
            if field not in parsed:
                logger.warning(f"Missing required field in reflection result: {field}")
                return None

        return parsed
    except Exception as e:
        logger.error(f"Error parsing reflection result: {e}")
        return None


def _is_user_approved_research(state: OrchestratorState) -> bool:
    """
    Check if user just approved a research request by looking at recent conversation.
    Returns True if the last assistant message asked for research confirmation
    and user responded positively.
    """
    conversation = state["conversation"]
    if len(conversation) < 2:
        return False

    prev_assistant_msg = None
    for i in range(len(conversation) - 2, -1, -1):
        if conversation[i].type == "ai":
            prev_assistant_msg = conversation[i]
            break

    if not prev_assistant_msg:
        return False

    metadata = prev_assistant_msg.additional_kwargs.get("message_metadata", {})
    was_confirmation = (
        metadata.get("response_mode") == ResponseMode.CONFIRMATION_REQUIRED
    )

    if not was_confirmation:
        return False

    user_msg = conversation[-1].content.lower().strip()
    approval_keywords = [
        "yes",
        "ok",
        "sure",
        "proceed",
        "go ahead",
        "continue",
        "approve",
    ]

    return any(keyword in user_msg for keyword in approval_keywords)


def is_user_rejected_research(state: OrchestratorState) -> bool:
    conversation = state["conversation"]
    if len(conversation) < 2:
        return False

    prev_assistant_msg = None
    for i in range(len(conversation) - 2, -1, -1):
        if getattr(conversation[i], "type", "") == "ai":
            prev_assistant_msg = conversation[i]
            break
    if not prev_assistant_msg:
        return False
    metadata = (prev_assistant_msg.additional_kwargs or {}).get("message_metadata", {})
    if metadata.get("response_mode") != ResponseMode.CONFIRMATION_REQUIRED:
        return False

    user_msg = (conversation[-1].content or "").lower().strip()
    rejection_keywords = [
        "no",
        "nope",
        "don't",
        "dont",
        "nah",
        "stop",
        "cancel",
        "reject",
        "decline",
        "không",
        "ko",
        "khong",
        "đừng",
        "dung",
        "khỏi",
        "khoi",
        "hủy",
        "huy",
        "không cần",
    ]
    return any(k in user_msg for k in rejection_keywords)


def extract_pending_route_from_prev_assistant(
    state: OrchestratorState,
) -> Optional[str]:
    conversation = state["conversation"]
    if len(conversation) < 2:
        return None
    prev_assistant_msg = None
    for i in range(len(conversation) - 2, -1, -1):
        if getattr(conversation[i], "type", "") == "ai":
            prev_assistant_msg = conversation[i]
            break
    if not prev_assistant_msg:
        return None
    metadata = (prev_assistant_msg.additional_kwargs or {}).get("message_metadata", {})
    if metadata.get("response_mode") != ResponseMode.CONFIRMATION_REQUIRED:
        return None
    return metadata.get("pending_route") or metadata.get("route")
