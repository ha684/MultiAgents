# src/agents/main.py
from typing import Dict, Any, List, Optional
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph
from src.agents.basic import response_agent, query_context_agent
from src.agents.basic.base import AgentBase
from src.llm.factory import get_llm
from src.utils.logger_conf import logger
from src.agents.graph.state import OrchestratorState
from src.agents.graph.prompts import PromptTemplates
from src.agents.graph.schemas import RouteDecision
from src.agents.graph.simple_search_graph import SimpleSearchGraph
from src.agents.graph.research_graph import ResearchGraph
from src.agents.tools.server.mcp_retrieve_tools import think
from src.services.types import Message
from src.common.types import TextPart, RetrievalContext
from src.utils import parse_response
from src.services.conversation_service import ConversationService
import tiktoken
import uuid
from src.db.models.conversation import MessageStatus


class OrchestratorGraph(AgentBase):
    """
    Main Orchestrator - Coordinates entire workflow with full conversation context
    """

    def __init__(self):
        self.llm = get_llm("nxchat")
        tokenizer = tiktoken.encoding_for_model("gpt-4o")
        self.simple_search_graph = SimpleSearchGraph(tokenizer)
        self.research_graph = ResearchGraph()
        self.conv_service = ConversationService()
        self.graph = self._build_graph()

    async def contextualize_query_node(
        self, state: OrchestratorState
    ) -> Dict[str, Any]:
        """Contextualize query before routing"""

        original_query = state["original_query"]

        if len(state["conversation"]) > 2:
            contextualized = await query_context_agent.ainvoke(
                history=state["conversation"]
            )
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
        router_llm = self.llm.bind_tools([think])

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

        result = await self.simple_search_graph.run(state)
        return {
            "final_answer": result["final_answer"],
            "cited_documents": result.get("cited_documents", []),
            "retrieval_contexts": result.get("retrieval_contexts", []),
            "response_metadata": result.get("response_metadata", {}),
        }

    async def research_subgraph_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """Execute research graph"""

        result = await self.research_graph.run(state)

        return {
            "accumulated_knowledge": result["accumulated_knowledge"],
            "all_search_history": result["all_search_history"],
            "used_rag_ids": result["used_rag_ids"],
            "used_web_urls": result["used_web_urls"],
            "iteration_count": result["iteration_count"],
        }

    async def fact_checker_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """Fact check accumulated knowledge"""

        if not state.get("accumulated_knowledge"):
            logger.warning("No knowledge to fact check")
            return {}

        system_prompt = SystemMessage(
            content="You are a fact-checking expert responsible for verifying and refining accumulated research knowledge before final synthesis."
        )
        user_prompt = HumanMessage(
            content=PromptTemplates.FACT_CHECKER_PROMPT.format(
                original_query=state["contextualized_query"],
                accumulated_knowledge=state["accumulated_knowledge"],
            )
        )
        messages = [system_prompt, user_prompt]

        fact_check_llm = self.llm.bind_tools([think])
        fact_checked_knowledge = await self.iterative_llm_call_text(
            messages=messages,
            llm_with_tools=fact_check_llm,
            available_tools={"think": think},
            max_iterations=3,
            retry_prompt="Please provide your answer again.",
            fallback_value=state["accumulated_knowledge"],
        )

        logger.info("Fact checking complete")

        return {"accumulated_knowledge": fact_checked_knowledge.content}

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

        if route == "simple_search":
            logger.info("Synthesizing simple search response")
            response = await response_agent.ainvoke(
                contexts=state["retrieval_contexts"][0]["cited_chunks"],
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

        cited_sources = []
        if state.get("used_rag_ids"):
            cited_sources.extend(
                [f"RAG:{doc_id}" for doc_id in state["used_rag_ids"][:10]]
            )
        if state.get("used_web_urls"):
            cited_sources.extend([f"Web:{url}" for url in state["used_web_urls"][:10]])

        return {
            "final_answer": final_synthesizer_response.content,
            "response_metadata": {
                "route": "deep_research",
                "search_method": "multi_step_research",
                "total_iterations": state.get("iteration_count", 0),
                "total_sources": len(cited_sources),
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

        # Add nodes
        workflow.add_node("contextualize_query", self.contextualize_query_node)
        workflow.add_node("router", self.router_node)
        workflow.add_node("simple_search_subgraph", self.simple_search_subgraph_node)
        workflow.add_node("research_subgraph_node", self.research_subgraph_node)
        workflow.add_node("fact_checker", self.fact_checker_node)
        workflow.add_node("final_synthesizer", self.final_synthesizer_node)

        # Entry point
        workflow.set_entry_point("contextualize_query")

        # Flow
        workflow.add_edge("contextualize_query", "router")

        workflow.add_conditional_edges(
            "router",
            self.route_after_router,
            {
                "chitchat": "final_synthesizer",
                "simple_search": "simple_search_subgraph",
                "research_subgraph": "research_subgraph_node",
            },
        )

        workflow.add_edge("research_subgraph_node", "fact_checker")
        workflow.add_edge("fact_checker", "final_synthesizer")
        workflow.add_edge("simple_search_subgraph", "final_synthesizer")

        workflow.set_finish_point("final_synthesizer")

        return workflow.compile()

    async def run(self, conversation: List[BaseMessage]) -> Dict[str, Any]:
        """
        Execute orchestrator graph with full conversation

        Args:
            conversation: Full conversation history (List[BaseMessage])
            metadata: The metadata of the search

        Returns:
            Dict with answer, metadata, contexts, and cited documents
        """
        try:
            original_query = conversation[-1].content
            conversation_metadata = conversation[-1].additional_kwargs.get(
                "message_metadata", {}
            )
            conversation_id = conversation_metadata.get("conversation_id")
            user_message_id = conversation_metadata.get("message_id")

            initial_state = OrchestratorState(
                conversation=conversation,
                original_query=original_query,
                contextualized_query="",
                route_decision=None,
                search_plan=None,
                pending_queries=[],
                completed_queries=[],
                accumulated_knowledge="",
                search_results=[],
                all_search_history=[],
                iteration_count=0,
                max_searches=0,
                used_rag_ids=[],
                used_web_urls=[],
                should_switch_search_type=False,
                verification_result=None,
                retrieval_contexts=[],
                final_answer="",
                response_metadata={},
            )

            result = await self.graph.ainvoke(initial_state)

            metadata: Dict[str, Any] = result.get("response_metadata", {})
            metadata.update({"route": result.get("route_decision")})
            used_rag_ids = result.get("used_rag_ids", [])
            used_web_urls = result.get("used_web_urls", [])
            metadata.update({"used_rag_ids": used_rag_ids})
            metadata.update({"used_web_urls": used_web_urls})

            message = Message(
                parts=[TextPart(type="text", text=result["final_answer"])],
                role="agent",
                metadata=metadata,
                retrieval_context=RetrievalContext(
                    **result.get("retrieval_contexts", [])[0]
                ),
            )

            await self.conv_service.add_message(message, conversation_id)

            if user_message_id:
                await self.conv_service.update_message_status(
                    uuid.UUID(user_message_id), MessageStatus.COMPLETED
                )

            return message
        except Exception as e:
            logger.error(f"Error running orchestrator graph: {e}")
            if user_message_id:
                await self.conv_service.update_message_status(
                    uuid.UUID(user_message_id), MessageStatus.FAILED
                )
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
