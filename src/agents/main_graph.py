# src/agents/main_graph.py
"""
Main Orchestrator Graph - Entry Point with Delegation
Routes to NormalGraph (fast path) or ThinkingGraph (iterative research)
"""

from typing import Any, AsyncGenerator, Dict, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.runnables.schema import StreamEvent
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.basic import response_agent
from src.agents.graph.base import GraphAgentBase
from src.agents.graph.normal_graph import NormalGraph
from src.agents.graph.thinking_graph import ThinkingGraph
from src.agents.shared.manager import execution_manager
from src.agents.shared.registry import enable_sql, seed_base_subgraphs
from src.domain.entities.graph import ResponseMode, RunConfig
from src.domain.entities.state import NormalGraphState, MainGraphState, ThinkingState
from src.domain.schemas.chat import Message, RetrievalContext, TextPart
from src.services.conversation_service import ConversationService
from src.agents.prompts.agent_prompts import PromptTemplates
from src.agents.tools.server.mcp_retrieve_tools import (
    use_normal_mode,
    use_thinking_mode,
)
from src.utils.logger_conf import logger


class MainGraph(GraphAgentBase[MainGraphState]):
    """
    Main Orchestrator - Entry Point with Intelligent Routing

    Flow:
    1. direct_response_node: Entry point with function calling
       - LLM decides: direct answer / normal mode / thinking mode
    2. Route to:
       - Direct answer → END
       - Normal mode → NormalGraph (fast path)
       - Thinking mode → ThinkingGraph (iterative research)
    """

    def __init__(self):
        """Initialize main graph, normal graph, and thinking graph."""
        super().__init__()
        self.conv_service = ConversationService()
        self.graph_name = "MainGraph"
        self.normal_graph = NormalGraph()
        self.thinking_graph = ThinkingGraph()

        self.compiled_graph = self._build_graph()
        seed_base_subgraphs()

    @property
    def graph(self) -> CompiledStateGraph:
        """Return the compiled graph."""
        return self.compiled_graph

    def default_run_config(self) -> RunConfig:
        """Return the default run configuration."""
        return RunConfig(
            graph_name=self.graph_name,
            recursion_limit=100,
            timeout_seconds=600,
        )

    async def direct_response_node(self, state: MainGraphState) -> Dict[str, Any]:
        """
        Entry point with intelligent routing.
        LLM decides: direct response / normal mode / thinking mode
        """
        conversation = state.get("conversation", [])
        system_prompt = SystemMessage(content=PromptTemplates.DIRECT_RESPONSE_PROMPT)
        messages = [system_prompt] + conversation
        llm_with_tools = self.llm.bind_tools(
            [use_normal_mode, use_thinking_mode]
        ).with_retry()
        try:
            response: AIMessage = await llm_with_tools.ainvoke(messages)

            if response.content and not response.tool_calls:
                logger.info("[DirectResponse] Agent chose to answer directly")
                return {
                    "route_mode": "direct",
                    "final_answer": response.content,
                }

            if response.tool_calls:
                tool_call = response.tool_calls[0]
                tool_name = tool_call["name"]

                logger.info(f"[DirectResponse] Agent called tool: {tool_name}")

                if tool_name == "use_normal_mode":
                    return {
                        "route_mode": "normal",
                    }
                elif tool_name == "use_thinking_mode":
                    return {
                        "route_mode": "thinking",
                    }
                else:
                    logger.warning(f"[DirectResponse] Unknown tool: {tool_name}")
                    return {
                        "route_mode": "direct",
                        "final_answer": "I apologize, but I encountered an issue. Could you please rephrase your question?",
                    }

            logger.warning("[DirectResponse] No content or tool calls in response")
            return {
                "route_mode": "direct",
                "final_answer": "I apologize, but I'm having trouble processing your request. Could you please rephrase?",
            }

        except Exception as e:
            logger.error(f"[DirectResponse] Error: {e}")
            return {
                "route_mode": "direct",
                "final_answer": "I apologize, but I encountered an error. Could you please try again?",
                "response_metadata": {
                    "error": str(e),
                },
            }

    def route_after_entry(self, state: MainGraphState) -> str:
        """Route after entry point based on mode decision."""
        route_mode = state.get("route_mode", "direct")

        logger.info(f"[Orchestrator] Routing to: {route_mode}")

        if route_mode == "direct":
            return "end"
        elif route_mode == "normal":
            return "execute_normal"
        elif route_mode == "thinking":
            return "execute_thinking"

        return "end"

    async def execute_normal_node(self, state: MainGraphState) -> Dict[str, Any]:
        """
        Execute NormalGraph and return results.
        Delegates to NormalGraph for fast path execution.
        """
        logger.info("[Orchestrator] Executing NormalGraph")

        try:
            conversation = state.get("conversation", [])
            normal_state = NormalGraphState(conversation=conversation)
            result = await self.normal_graph.ainvoke(normal_state)
            final_answer = result.state.get("final_answer", "")
            response_metadata = result.state.get("response_metadata", {})
            cited_documents = result.state.get("cited_documents", [])

            logger.info(
                f"[Orchestrator] NormalGraph completed with {len(cited_documents)} citations"
            )

            return {
                "final_answer": final_answer,
                "response_metadata": response_metadata,
                "cited_documents": cited_documents,
            }

        except Exception as e:
            logger.error(f"[Orchestrator] Error executing NormalGraph: {e}")
            error_response = await response_agent.ainvoke(state)
            return {
                "final_answer": error_response.content,
                "response_metadata": {
                    "mode": "normal",
                    "error": str(e),
                    "response_mode": ResponseMode.NO_VIABLE_OPTION,
                },
            }

    async def execute_thinking_node(self, state: MainGraphState) -> Dict[str, Any]:
        """
        Execute ThinkingGraph and return results.
        Delegates to ThinkingGraph for iterative research.
        """
        logger.info("[Orchestrator] Executing ThinkingGraph")

        try:
            conversation = state.get("conversation", [])
            thinking_state = ThinkingState(conversation=conversation)

            result = await self.thinking_graph.ainvoke(thinking_state)
            final_answer = result.state.get("final_answer", "")
            response_metadata = result.state.get("response_metadata", {})
            cited_documents = result.state.get("cited_documents", [])
            return {
                "final_answer": final_answer,
                "response_metadata": response_metadata,
                "cited_documents": cited_documents,
            }

        except Exception as e:
            logger.error(f"[Orchestrator] Error executing ThinkingGraph: {e}")

            error_response = await response_agent.ainvoke(state)
            return {
                "final_answer": error_response.content,
                "response_metadata": {
                    "mode": "thinking",
                    "error": str(e),
                    "response_mode": ResponseMode.NO_VIABLE_OPTION,
                },
            }

    def _build_graph(self) -> CompiledStateGraph:
        """Build the main graph."""
        workflow = StateGraph(MainGraphState)

        workflow.add_node("direct_response", self.direct_response_node)
        workflow.add_node("execute_normal", self.execute_normal_node)
        workflow.add_node("execute_thinking", self.execute_thinking_node)

        workflow.set_entry_point("direct_response")

        workflow.add_conditional_edges(
            "direct_response",
            self.route_after_entry,
            {
                "end": END,
                "execute_normal": "execute_normal",
                "execute_thinking": "execute_thinking",
            },
        )

        workflow.add_edge("execute_normal", END)
        workflow.add_edge("execute_thinking", END)

        return workflow.compile(name=self.graph_name)

    async def astream(
        self, conversation: List[BaseMessage]
    ) -> AsyncGenerator[StreamEvent, None]:
        """Run the main graph on the entire conversation (streaming)."""
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

        initial_state = MainGraphState(
            conversation=conversation,
            subgraph_policy=subgraph_policy,
            search_iterations=[],
            current_iteration=1,
            accumulated_context="",
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
        """Non-streaming execution."""
        try:
            initial_state = MainGraphState(
                conversation=conversation,
                search_iterations=[],
                current_iteration=1,
                accumulated_context="",
            )
            final_result = await super().ainvoke(initial_state)
            message = Message(
                parts=[
                    TextPart(
                        type="text", text=final_result.state.get("final_answer", "")
                    )
                ],
                role="agent",
                metadata=final_result.state.get("response_metadata", {}),
                retrieval_context=RetrievalContext(
                    **final_result.state.get("retrieval_contexts", {})
                ),
            )
            return message
        except Exception as e:
            logger.error(f"Error running main graph: {e}")
            raise e
