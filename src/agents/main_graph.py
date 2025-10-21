# src/agents/main_graph.py
import asyncio
from typing import Any, AsyncGenerator, Dict, List, Optional
import json
import tiktoken

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables.schema import StreamEvent
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph
from langchain_core.messages import get_buffer_string

from src.agents.basic import query_context_agent, response_agent
from src.agents.graph.base import GraphAgentBase, RunConfig
from src.agents.com.manager import execution_manager
from src.agents.com.registry import SubgraphRegistry
from src.agents.graph.prompts import PromptTemplates
from src.agents.graph.research_graph import ResearchGraph
from src.agents.graph.schemas import RouteDecision
from src.agents.graph.simple_search_graph import SimpleSearchGraph
from src.agents.graph.sql_graph import SqlGraph
from src.agents.graph.state import (
    OrchestratorState,
    ResearchState,
    SimpleSearchState,
    SqlState,
)
from src.agents.tools.server.mcp_retrieve_tools import think
from src.common.types import Message, RetrievalContext, TextPart
from src.llm.factory import get_llm
from src.services.conversation_service import ConversationService
from src.agents.graph.schemas import ResponseMode
from src.utils import parse_response
from src.utils.logger_conf import logger


class OrchestratorGraph(GraphAgentBase[OrchestratorState]):
    """
    Agentic Orchestrator - Acts as Planner/Dispatcher with:
    - Dynamic subgraph discovery via registry
    - Multi-step coordination & fallback
    - Simplified output via response_agent with modes
    """

    MAX_RETRY_ATTEMPTS = 3

    def __init__(self):
        self.llm = get_llm(provider="nxchat")
        self.thinking_llm = self.llm.bind_tools([think])
        tokenizer = tiktoken.encoding_for_model("gpt-4o")

        self.simple_search_graph = SimpleSearchGraph(tokenizer)
        self.research_graph = ResearchGraph()
        self.sql_graph = SqlGraph()

        self.conv_service = ConversationService()
        self.graph_name = "OrchestratorGraph"
        self.compiled_graph = self._build_graph()

    def _get_original_query(self, state: OrchestratorState) -> str:
        """Extract original query from last message in conversation"""
        return state["conversation"][-1].content

    async def _run_simple_search(
        self, state: OrchestratorState, web_active: bool
    ) -> Dict[str, Any]:
        conv = list(state["conversation"])
        if not conv:
            raise ValueError("Conversation is empty.")

        last = conv[-1]
        addl = getattr(last, "additional_kwargs", {}) or {}
        meta = dict(addl.get("message_metadata", {}))
        wsc = meta.get("web_search_config")

        if wsc is None and web_active:
            raise ValueError(
                "web_search_config is required for web search but was not found."
            )

        if wsc is not None:
            try:
                wsc = wsc.model_copy(update={"active": web_active})
            except Exception:
                wsc.active = web_active
            meta["web_search_config"] = wsc

        addl["message_metadata"] = meta
        conv[-1] = type(last)(**{**last.__dict__, "additional_kwargs": addl})

        simple_search_state = SimpleSearchState(
            conversation=conv,
            original_query=self._get_original_query(state),
            contextualized_query=state["contextualized_query"],
        )
        result = await self.simple_search_graph.ainvoke(state=simple_search_state)
        return {
            "main_context": None,
            "cited_documents": result.get("cited_documents", []),
            "response_metadata": result.get("response_metadata", {}),
            "subgraph_error": None,
        }

    async def _execute_rag_search(self, state: OrchestratorState) -> Dict[str, Any]:
        return await self._run_simple_search(state, web_active=False)

    async def _execute_web_search(self, state: OrchestratorState) -> Dict[str, Any]:
        return await self._run_simple_search(state, web_active=True)

    async def _execute_research(self, state: OrchestratorState) -> Dict[str, Any]:
        """Execute research subgraph"""
        context_metadata = state["conversation"][-1].additional_kwargs.get(
            "message_metadata", {}
        )
        research_state = ResearchState(
            contextualized_query=state["contextualized_query"],
            context_metadata=context_metadata,
        )
        execution = execution_manager.get_execution(
            state["conversation"][-1].additional_kwargs.get("conversation_id")
        )

        research_task = asyncio.create_task(
            self.research_graph.ainvoke(state=research_state)
        )

        done, pending = await asyncio.wait(
            [research_task, asyncio.create_task(execution.skip_event.wait())],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        if execution.should_skip():
            logger.warning("User requested skip during research")
            result = execution.partial_state or {
                "accumulated_knowledge": "",
                "cited_documents": [],
            }
        else:
            result = await research_task
            execution.update_partial_state(result)

        return {
            "main_context": result.get("accumulated_knowledge", ""),
            "cited_documents": result.get("cited_documents", []),
            "response_metadata": {},
            "subgraph_error": None,
        }

    async def _execute_sql_query(self, state: OrchestratorState) -> Dict[str, Any]:
        """Execute SQL query subgraph"""
        sql_state = SqlState(contextualized_query=state["contextualized_query"])
        result = await self.sql_graph.ainvoke(state=sql_state)

        results_text = ""
        query_results = result.get("query_results")
        if query_results:
            results_text = f"Original Question: {state['contextualized_query']}\n\n"
            results_text += "Query Results:\n\n"

            for res in query_results:
                if res.get("success"):
                    results_text += f"Purpose: {res['purpose']}\n"
                    results_text += f"Rows returned: {res['row_count']}\n"
                    if res.get("results"):
                        results_text += "Sample data (first 3 rows):\n"
                        results_text += json.dumps(
                            res["results"][:3], indent=2, default=str
                        )
                    results_text += "\n\n"

            if result.get("chart_spec"):
                results_text += "Note: A visualization chart has also been generated for this data.\n"

        response_metadata = result.get("response_metadata", {})
        if result.get("chart_spec"):
            response_metadata["sql_chart_spec"] = result["chart_spec"]

        return {
            "main_context": results_text,
            "cited_documents": [],
            "response_metadata": response_metadata,
            "subgraph_error": result.get("sql_error"),
        }

    @property
    def graph(self) -> CompiledStateGraph:
        return self.compiled_graph

    def default_run_config(self) -> RunConfig:
        return RunConfig(
            graph_name=self.graph_name, recursion_limit=100, timeout_seconds=600
        )

    async def contextualize_query_node(
        self, state: OrchestratorState
    ) -> Dict[str, Any]:
        """Contextualize query before routing"""
        original_query = self._get_original_query(state)

        if len(state["conversation"]) > 2:
            contextualized = await query_context_agent.ainvoke(
                history=state["conversation"]
            )
            contextualized = contextualized.content
            logger.info(f"Contextualized: '{original_query}' → '{contextualized}'")
        else:
            contextualized = original_query
            logger.info("No history - using original query")

        return {"contextualized_query": contextualized}

    def _check_if_user_approved_research(self, state: OrchestratorState) -> bool:
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

    async def router_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """Dynamic router using registry definitions"""
        max_iterations = 3
        conversation = state["conversation"]

        subgraph_definitions = SubgraphRegistry.get_definitions()
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

        conversation_context = ""
        if len(conversation) > 1:
            recent_messages = conversation[-4:-1]
            conversation_context = get_buffer_string(recent_messages)

        system_prompt = SystemMessage(content=PromptTemplates.ROUTER_PROMPT)

        context_message = HumanMessage(
            content=f"""<available_subgraphs>
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

        messages: List[BaseMessage] = [system_prompt, context_message]
        router_llm = self.thinking_llm

        response = await self.iterative_llm_call_structured(
            messages=messages,
            llm_with_tools=router_llm,
            available_tools={"think": think},
            max_iterations=max_iterations,
            parse_fn=parse_route_decision,
            retry_prompt="Please provide the route decision in correct JSON format with 'route' key matching one of the available subgraph names.",
        )

        if not response:
            logger.warning("No route decision provided, defaulting to direct_response")
            return {
                "route_decision": "direct_response",
            }

        route = response["route"]

        if not SubgraphRegistry.get_subgraph(route):
            logger.error(
                f"Router selected invalid route: {route}, defaulting to direct_response"
            )
            route = "direct_response"

        subgraph_config = SubgraphRegistry.get_subgraph(route)
        if subgraph_config and subgraph_config.requires_confirmation:
            if not self._check_if_user_approved_research(state):
                logger.info(f"Route {route} requires confirmation, asking user first")
                return {
                    "route_decision": route,
                    "needs_confirmation": True,
                }
            else:
                logger.info(f"User approved {route}, proceeding with execution")

        return {
            "route_decision": route,
            "needs_confirmation": False,
        }

    def _determine_response_mode_from_result(
        self, state: OrchestratorState, route: str, result: Dict[str, Any]
    ) -> str:
        """
        Centralized logic to determine response mode based on execution result.
        Called AFTER subgraph execution.
        """
        execution_history = state.get("execution_history", [])

        if state.get("needs_confirmation", False):
            return ResponseMode.CONFIRMATION_REQUIRED

        if result.get("subgraph_error"):
            return ResponseMode.ERROR

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
        """
        Dispatcher that executes the selected subgraph and handles errors with retry logic
        """
        route = state["route_decision"]

        if state.get("needs_confirmation", False):
            response_mode = self._determine_response_mode_from_result(state, route, {})
            return {
                "subgraph_result": "needs_confirmation",
                "response_mode": response_mode,
                "main_context": "",
                "cited_documents": [],
                "response_metadata": {},
            }

        if route == "direct_response":
            response_mode = self._determine_response_mode_from_result(state, route, {})
            return {
                "subgraph_result": "direct_response",
                "response_mode": response_mode,
                "main_context": "",
                "cited_documents": [],
                "response_metadata": {},
            }

        subgraph_config = SubgraphRegistry.get_subgraph(route)
        if not subgraph_config or not subgraph_config.executor:
            logger.error(f"Unknown or non-executable subgraph: {route}")
            error_result = {"subgraph_error": f"Unknown subgraph: {route}"}
            response_mode = self._determine_response_mode_from_result(
                state, route, error_result
            )
            return {
                "subgraph_result": "error",
                "subgraph_error": f"Unknown subgraph: {route}",
                "response_mode": response_mode,
                "main_context": "",
                "cited_documents": [],
                "response_metadata": {},
            }

        executor_name = subgraph_config.executor
        method_name = f"_execute_{executor_name}"
        executor_method = getattr(self, method_name, None)

        if not executor_method or not callable(executor_method):
            error_msg = f"Executor method '{method_name}' not found or not callable in OrchestratorGraph."
            logger.error(error_msg)
            error_result = {"subgraph_error": error_msg}
            response_mode = self._determine_response_mode_from_result(
                state, route, error_result
            )
            return {
                "subgraph_result": "error",
                "subgraph_error": error_msg,
                "response_mode": response_mode,
                "main_context": "",
                "cited_documents": [],
                "response_metadata": {},
            }

        execution_history = state.get("execution_history", [])

        if len(execution_history) >= self.MAX_RETRY_ATTEMPTS:
            logger.warning(
                f"Max retry attempts ({self.MAX_RETRY_ATTEMPTS}) reached, switching to direct_response"
            )
            error_result = {"subgraph_error": "Max retry attempts exceeded"}
            response_mode = ResponseMode.NO_VIABLE_OPTION
            return {
                "subgraph_result": "exhausted",
                "subgraph_error": "All retrieval options exhausted after multiple attempts",
                "response_mode": response_mode,
                "execution_history": execution_history,
                "route_decision": "direct_response",
                "main_context": "",
                "cited_documents": [],
                "response_metadata": {},
            }

        try:
            logger.info(f"Executing subgraph via method: {method_name}")

            result = await executor_method(state)

            has_result = bool(
                result.get("main_context") or result.get("cited_documents")
            )

            if not has_result:
                logger.warning(f"Subgraph {route} returned no useful result")

                execution_history.append(
                    {"subgraph": route, "error": "No useful result", "timestamp": "now"}
                )

                if (
                    subgraph_config.fallback_chain
                    and len(execution_history) < self.MAX_RETRY_ATTEMPTS
                ):
                    next_fallback = subgraph_config.fallback_chain[0]
                    logger.info(f"Trying fallback chain: {next_fallback}")

                    retry_result = {
                        **result,
                        "subgraph_error": "No result, retrying with fallback",
                    }
                    response_mode = self._determine_response_mode_from_result(
                        state, next_fallback, retry_result
                    )

                    return {
                        **result,
                        "subgraph_result": "retry",
                        "execution_history": execution_history,
                        "response_mode": response_mode,
                        "route_decision": next_fallback,
                    }
                else:
                    logger.warning(
                        "No fallback available or max retries reached, switching to direct_response"
                    )
                    no_result = {**result, "subgraph_error": "No result found"}
                    response_mode = self._determine_response_mode_from_result(
                        state, "direct_response", no_result
                    )

                    return {
                        **result,
                        "subgraph_result": "no_result",
                        "execution_history": execution_history,
                        "response_mode": response_mode,
                        "route_decision": "direct_response",
                    }

            logger.info(f"Subgraph {route} completed successfully")
            response_mode = self._determine_response_mode_from_result(
                state, route, result
            )

            return {
                **result,
                "subgraph_result": "success",
                "response_mode": response_mode,
                "execution_history": execution_history,
            }

        except Exception as e:
            logger.error(f"Error executing subgraph {route}: {e}")

            execution_history.append({"subgraph": route, "error": str(e)})

            if (
                subgraph_config.fallback_chain
                and len(execution_history) < self.MAX_RETRY_ATTEMPTS
            ):
                next_fallback = subgraph_config.fallback_chain[0]
                logger.info(f"Exception occurred, trying fallback: {next_fallback}")

                error_result = {"subgraph_error": str(e)}
                response_mode = self._determine_response_mode_from_result(
                    state, next_fallback, error_result
                )

                return {
                    "subgraph_result": "retry",
                    "subgraph_error": str(e),
                    "execution_history": execution_history,
                    "response_mode": response_mode,
                    "route_decision": next_fallback,
                    "main_context": "",
                    "cited_documents": [],
                    "response_metadata": {},
                }
            else:
                logger.error(
                    "Exception with no fallback available, switching to direct_response"
                )
                error_result = {"subgraph_error": str(e)}
                response_mode = ResponseMode.NO_VIABLE_OPTION

                return {
                    "subgraph_result": "error",
                    "subgraph_error": str(e),
                    "execution_history": execution_history,
                    "response_mode": response_mode,
                    "route_decision": "direct_response",
                    "main_context": "",
                    "cited_documents": [],
                    "response_metadata": {},
                }

    async def final_response_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """
        Universal response handler - delegates to response_agent with appropriate mode
        All output formatting logic is handled by response_agent
        """
        route = state.get("route_decision")
        response_mode = state.get("response_mode", ResponseMode.STANDARD)

        logger.info(f"Final response with mode: {response_mode}, route: {route}")

        response = await response_agent.ainvoke(
            contexts=state.get("cited_documents", []),
            history=state["conversation"],
            mode=response_mode,
            accumulated_knowledge=state.get("main_context", ""),
            execution_history=state.get("execution_history", []),
            error_message=state.get("subgraph_error"),
            pending_route=route
            if response_mode == ResponseMode.CONFIRMATION_REQUIRED
            else None,
        )

        response_metadata = state.get("response_metadata", {})
        response_metadata.update(
            {
                "route": route,
                "response_mode": response_mode,
                "execution_history": state.get("execution_history", []),
            }
        )

        return {
            "final_answer": response.content,
            "response_metadata": response_metadata,
        }

    def route_after_dispatch(self, state: OrchestratorState) -> str:
        """Decide next step after subgraph execution"""
        result = state.get("subgraph_result", "success")

        if result == "retry":
            logger.info("Retrying with fallback route")
            return "router"
        elif result == "needs_confirmation":
            logger.info("Going to response to ask for confirmation")
            return "final_response"
        else:
            return "final_response"

    def _build_graph(self) -> CompiledStateGraph:
        """Build agentic orchestrator graph"""
        workflow = StateGraph(OrchestratorState)

        workflow.add_node("contextualize_query", self.contextualize_query_node)
        workflow.add_node("router", self.router_node)
        workflow.add_node("dispatch_subgraph", self.dispatch_subgraph_node)
        workflow.add_node("final_response", self.final_response_node)

        workflow.set_entry_point("contextualize_query")

        workflow.add_edge("contextualize_query", "router")
        workflow.add_edge("router", "dispatch_subgraph")

        workflow.add_conditional_edges(
            "dispatch_subgraph",
            self.route_after_dispatch,
            {"router": "router", "final_response": "final_response"},
        )

        workflow.set_finish_point("final_response")

        return workflow.compile(name=self.graph_name)

    async def astream(
        self, conversation: List[BaseMessage]
    ) -> AsyncGenerator[StreamEvent, None]:
        """Execute orchestrator graph with full conversation"""
        initial_state = OrchestratorState(
            conversation=conversation,
            contextualized_query=None,
            route_decision=None,
            response_mode=None,
            execution_history=[],
            subgraph_result=None,
            subgraph_error=None,
            main_context=None,
            cited_documents=None,
            final_answer=None,
            response_metadata=None,
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
            original_query = conversation[-1].content
            initial_state = OrchestratorState(
                conversation=conversation,
                original_query=original_query,
                execution_history=[],
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
