# src/agents/main_graph.py
import asyncio
from typing import Any, AsyncGenerator, Dict, List, Optional

import tiktoken
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables.schema import StreamEvent
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.basic import query_context_agent, response_agent
from src.agents.graph.base import GraphAgentBase, RunConfig
from src.agents.com.manager import execution_manager
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
from src.utils import parse_response
from src.utils.logger_conf import logger


class OrchestratorGraph(GraphAgentBase[OrchestratorState]):
    """
    Main Orchestrator - Coordinates entire workflow with full conversation context
    """

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

        original_query = state["original_query"]

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

    async def router_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """Route with structured output"""

        max_iterations = 3
        conversation = state["conversation"]

        system_prompt = SystemMessage(content=PromptTemplates.ROUTER_PROMPT)
        messages: List[BaseMessage] = [system_prompt] + conversation
        router_llm = self.thinking_llm

        response = await self.iterative_llm_call_structured(
            messages=messages,
            llm_with_tools=router_llm,
            available_tools={"think": think},
            max_iterations=max_iterations,
            parse_fn=parse_route_decision,
            retry_prompt="Please provide the route decision in correct JSON format.",
        )

        if not response:
            logger.warning("No route decision provided")
            return {"route_decision": "chitchat"}

        return {"route_decision": response["route"]}

    async def simple_search_subgraph_node(
        self, state: OrchestratorState
    ) -> Dict[str, Any]:
        """Execute simple search graph"""

        simple_search_state = SimpleSearchState(
            conversation=state["conversation"],
            original_query=state["original_query"],
            contextualized_query=state["contextualized_query"],
        )

        result = await self.simple_search_graph.ainvoke(state=simple_search_state)
        return {
            "retrieval_contexts": result.get("retrieval_contexts", {}),
            "response_metadata": result.get("response_metadata", {}),
        }

    async def research_subgraph_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """Execute research graph"""
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

        if execution.should_skip():
            logger.warning("⏭️ User requested skip")
            research_task.cancel()

            partial = execution.partial_state or research_state
            return ResearchState(
                contextualized_query=research_state.contextualized_query,
                context_metadata=research_state.context_metadata,
                accumulated_knowledge=partial.get(
                    "accumulated_knowledge", "[Research skipped by user]"
                ),
                all_search_history=partial.get("all_search_history", []),
                cited_documents=partial.get("cited_documents", []),
            )

        return await research_task

    async def sql_subgraph_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """Execute SQL query graph"""

        sql_state = SqlState(
            conversation=state["conversation"],
            original_query=state["original_query"],
            contextualized_query=state["contextualized_query"],
            database_schema=None,
            generated_sql=None,
            validation_result=None,
            sql_error=None,
            query_results=None,
            result_summary=None,
            response_metadata={},
        )

        result = await self.sql_graph.ainvoke(state=sql_state)

        return {
            "final_answer": result.get("result_summary", ""),
            "response_metadata": result.get("response_metadata", {}),
        }

    async def final_synthesizer_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """Generate final response"""

        route = state.get("route_decision")
        if route == "chitchat":
            logger.info("Synthesizing chitchat response")
            response = await response_agent.ainvoke(
                contexts=[], history=state["conversation"]
            )
            response_metadata = state.get("response_metadata", {})
            response_metadata.update({"route": "chitchat", "search_method": "none"})
            return {
                "final_answer": response.content,
                "response_metadata": response_metadata,
            }

        if route == "sql_query":
            logger.info("SQL query already processed - returning result")
            return {
                "final_answer": state.get("final_answer", ""),
                "response_metadata": state.get("response_metadata", {}),
            }

        if route == "simple_search":
            logger.info("Synthesizing simple search response")
            response = await response_agent.ainvoke(
                contexts=state["retrieval_contexts"].get("cited_chunks", []),
                history=state["conversation"],
            )
            response_metadata = state.get("response_metadata", {})
            response_metadata.update({"route": "simple_search"})
            return {
                "final_answer": response.content,
                "response_metadata": response_metadata,
            }

        logger.info("Synthesizing research response")
        user_message = state["conversation"][-1].content
        system_prompt = SystemMessage(
            content="You are a research synthesis expert tasked with creating a comprehensive, well-structured response based on accumulated research findings."
        )
        user_prompt = HumanMessage(
            content=PromptTemplates.FINAL_SYNTHESIZER_PROMPT.format(
                user_message=user_message,
                accumulated_knowledge=state.get("accumulated_knowledge", ""),
            )
        )
        messages = [system_prompt] + state["conversation"][-1:] + [user_prompt]

        final_synthesizer_response = await self.simple_llm_call(
            messages=messages, llm=self.llm
        )

        return {
            "final_answer": final_synthesizer_response.content,
            "response_metadata": {
                "route": "deep_research",
                "search_method": "multi_step_research",
            },
        }

    def route_after_router(self, state: OrchestratorState) -> str:
        """Route after classification"""
        decision = state["route_decision"]
        logger.info(f"Routing to: {decision}")
        return decision

    def _build_graph(self) -> CompiledStateGraph:
        """Build orchestrator graph"""
        workflow = StateGraph(OrchestratorState)

        workflow.add_node("contextualize_query", self.contextualize_query_node)
        workflow.add_node("router", self.router_node)
        workflow.add_node("simple_search_subgraph", self.simple_search_subgraph_node)
        workflow.add_node("research_subgraph_node", self.research_subgraph_node)
        workflow.add_node("sql_subgraph_node", self.sql_subgraph_node)
        workflow.add_node("final_synthesizer", self.final_synthesizer_node)

        workflow.set_entry_point("contextualize_query")

        workflow.add_edge("contextualize_query", "router")

        workflow.add_conditional_edges(
            "router",
            self.route_after_router,
            {
                "chitchat": "final_synthesizer",
                "simple_search": "simple_search_subgraph",
                "deep_research": "research_subgraph_node",
                "sql_query": "sql_subgraph_node",
            },
        )

        workflow.add_edge("research_subgraph_node", "final_synthesizer")
        workflow.add_edge("simple_search_subgraph", "final_synthesizer")
        workflow.add_edge("sql_subgraph_node", "final_synthesizer")

        workflow.set_finish_point("final_synthesizer")

        return workflow.compile(name=self.graph_name)

    async def stream(
        self, conversation: List[BaseMessage]
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Execute orchestrator graph with full conversation
        """
        original_query = conversation[-1].content

        initial_state = OrchestratorState(
            conversation=conversation,
            original_query=original_query,
            contextualized_query="",
            route_decision=None,
            accumulated_knowledge="",
            cited_documents=[],
            retrieval_contexts={},
            final_answer="",
            response_metadata={},
        )

        config = {"recursion_limit": 100}
        timeout_seconds = 600
        conversation_id = conversation[-1].additional_kwargs.get("conversation_id")
        execution_manager.start_execution(conversation_id)

        try:
            async with asyncio.timeout(timeout_seconds):
                async for event in self.compiled_graph.astream_events(
                    initial_state, config=config, version="v2"
                ):
                    last_known_state = event
                    yield event
        except asyncio.TimeoutError:
            logger.warning(
                f"⚠️ 'OrchestratorGraph' timed out after {timeout_seconds} seconds. "
                f"Returning the most recent accumulated result."
            )
            yield last_known_state
        except Exception as e:
            logger.error(
                f"❌ 'OrchestratorGraph' encountered an unexpected error: {e}. "
                "Returning the most recent accumulated result."
            )
            yield last_known_state
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
                contextualized_query="",
                route_decision=None,
                accumulated_knowledge="",
                cited_documents=[],
                retrieval_contexts={},
                final_answer="",
                response_metadata={},
            )
            final_result = await self.compiled_graph.ainvoke(initial_state)
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
