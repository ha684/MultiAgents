# src/agents/main.py
from typing import Dict, Any, List
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from src.agents.basic import response_agent, query_context_agent
from src.utils.logger_conf import logger
from src.agents.graph.state import AgentState
from src.agents.graph.prompts import PromptTemplates
from src.agents.graph.schemas import RouteDecision
from src.agents.graph.simple_search_graph import SimpleSearchGraph
from src.agents.graph.research_graph import ResearchGraph
import tiktoken


class OrchestratorGraph:
    """
    Main Orchestrator - Coordinates entire workflow with full conversation context
    """

    def __init__(self):
        self.haiku = ChatAnthropic(model="claude-3-5-haiku-20241022", temperature=0)
        self.sonnet = ChatAnthropic(model="claude-3-5-sonnet-20241022", temperature=0)
        self.opus = ChatAnthropic(model="claude-opus-4-20250514", temperature=0)

        tokenizer = tiktoken.encoding_for_model("gpt-4o")
        self.simple_search_graph = SimpleSearchGraph(tokenizer)
        self.research_graph = ResearchGraph()

        self.graph = self._build_graph()

    # =========================================================================
    # HELPER
    # =========================================================================

    def _format_conversation(self, conversation: List[BaseMessage]) -> str:
        """Format conversation for prompts"""
        formatted = []
        for msg in conversation:
            role = "Human" if isinstance(msg, HumanMessage) else "Assistant"
            formatted.append(f"{role}: {msg.content}")
        return "\n".join(formatted)

    # =========================================================================
    # NODES
    # =========================================================================

    async def contextualize_query_node(self, state: AgentState) -> Dict[str, Any]:
        """Contextualize query before routing"""
        logger.info("Orchestrator - Contextualizing query")

        original_query = state["original_query"]

        if len(state["conversation"]) > 2:
            contextualized = await query_context_agent.contextualize_query(
                history=state["conversation"]
            )
            logger.info(f"Contextualized: '{original_query}' → '{contextualized}'")
        else:
            contextualized = original_query
            logger.info("No history - using original query")

        return {"contextualized_query": contextualized}

    async def router_node(self, state: AgentState) -> Dict[str, Any]:
        """Route with structured output"""
        conversation_text = self._format_conversation(state["conversation"])

        prompt = PromptTemplates.ROUTER_PROMPT.format(
            conversation=conversation_text, query=state["contextualized_query"]
        )

        router_llm = self.haiku.with_structured_output(RouteDecision).with_retry(
            stop_after_attempt=3
        )

        decision = await router_llm.ainvoke(prompt)
        decision_dict = decision.model_dump()

        logger.info(f"Route: {decision_dict['route']}")
        logger.info(f"Reasoning: {decision_dict['reasoning']}")

        return {"route_decision": decision_dict["route"]}

    async def simple_search_node(
        self, state: AgentState, tool_context: Any
    ) -> Dict[str, Any]:
        """Execute simple search graph"""
        logger.info("Orchestrator - Simple Search")

        result = await self.simple_search_graph.run(state, tool_context)

        return {
            "final_answer": result["final_answer"],
            "cited_documents": result.get("cited_documents", []),
            "retrieval_contexts": result.get("retrieval_contexts", []),
            "response_metadata": result.get("response_metadata", {}),
        }

    async def research_subgraph_node(
        self, state: AgentState, tool_context: Any
    ) -> Dict[str, Any]:
        """Execute research graph"""
        logger.info("Orchestrator - Research Subgraph")

        result = await self.research_graph.run(state, tool_context)

        return {
            "accumulated_knowledge": result["accumulated_knowledge"],
            "all_search_history": result["all_search_history"],
            "used_rag_ids": result["used_rag_ids"],
            "used_web_urls": result["used_web_urls"],
            "iteration_count": result["iteration_count"],
        }

    async def fact_checker_node(self, state: AgentState) -> Dict[str, Any]:
        """Fact check accumulated knowledge"""
        logger.info("Orchestrator - Fact Checker")

        if not state.get("accumulated_knowledge"):
            logger.warning("No knowledge to fact check")
            return {}

        prompt = PromptTemplates.FACT_CHECKER_PROMPT.format(
            original_query=state["contextualized_query"],
            accumulated_knowledge=state["accumulated_knowledge"],
        )

        response = await self.sonnet.ainvoke(prompt)
        verified = response.content

        logger.info("Fact checking complete")

        return {"accumulated_knowledge": verified}

    async def final_synthesizer_node(self, state: AgentState) -> Dict[str, Any]:
        """Generate final response"""
        logger.info("Orchestrator - Final Synthesizer")

        route = state.get("route_decision")

        # Chitchat - direct response
        if route == "chitchat":
            logger.info("Synthesizing chitchat response")
            response = await response_agent.generate_response(
                contexts=[], history=state["conversation"]
            )

            return {
                "final_answer": response.content
                if hasattr(response, "content")
                else str(response),
                "response_metadata": {"route": "chitchat", "search_method": "none"},
            }

        # Simple search - already has answer
        if route == "simple_search":
            logger.info("Simple search complete")
            return {}

        # Deep research - synthesize from accumulated knowledge
        logger.info("Synthesizing research response")

        conversation_text = self._format_conversation(state["conversation"])

        prompt = PromptTemplates.FINAL_SYNTHESIZER_PROMPT.format(
            conversation=conversation_text,
            accumulated_knowledge=state.get("accumulated_knowledge", ""),
        )

        response = await self.opus.ainvoke(prompt)

        # Collect cited sources
        cited_sources = []
        if state.get("used_rag_ids"):
            cited_sources.extend(
                [f"RAG:{doc_id}" for doc_id in state["used_rag_ids"][:10]]
            )
        if state.get("used_web_urls"):
            cited_sources.extend([f"Web:{url}" for url in state["used_web_urls"][:10]])

        logger.info("=" * 80)
        logger.info("ORCHESTRATOR COMPLETE - Deep Research")
        logger.info(f"Sources: {len(cited_sources)}")
        logger.info(f"Iterations: {state.get('iteration_count', 0)}")
        logger.info("=" * 80)

        return {
            "final_answer": response.content,
            "response_metadata": {
                "route": "deep_research",
                "search_method": "multi_step_research",
                "total_iterations": state.get("iteration_count", 0),
                "total_sources": len(cited_sources),
            },
        }

    # =========================================================================
    # ROUTING
    # =========================================================================

    def route_after_router(self, state: AgentState) -> str:
        """Route after classification"""
        decision = state["route_decision"]

        route_map = {
            "chitchat": "final_synthesizer",
            "simple_search": "simple_search",
            "deep_research": "research_subgraph",
        }

        destination = route_map.get(decision, "final_synthesizer")
        logger.info(f"Routing to: {destination}")

        return destination

    # =========================================================================
    # GRAPH CONSTRUCTION
    # =========================================================================

    def _build_graph(self) -> CompiledStateGraph:
        """Build orchestrator graph"""
        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("contextualize_query", self.contextualize_query_node)
        workflow.add_node("router", self.router_node)
        workflow.add_node("simple_search", self.simple_search_node)
        workflow.add_node("research_subgraph", self.research_subgraph_node)
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
                "simple_search": "simple_search",
                "research_subgraph": "research_subgraph",
            },
        )

        workflow.add_edge("research_subgraph", "fact_checker")
        workflow.add_edge("fact_checker", "final_synthesizer")
        workflow.add_edge("simple_search", "final_synthesizer")
        workflow.add_edge("final_synthesizer", END)

        return workflow.compile()

    # =========================================================================
    # PUBLIC INTERFACE
    # =========================================================================

    async def run(
        self, conversation: List[BaseMessage], tool_context: Any
    ) -> Dict[str, Any]:
        """
        Execute orchestrator graph with full conversation

        Args:
            conversation: Full conversation history (List[BaseMessage])
            tool_context: Context for tool execution

        Returns:
            Dict with answer, metadata, contexts, and cited documents
        """
        # Extract latest query
        original_query = conversation[-1].content

        # Initialize state
        initial_state = AgentState(
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
            cited_documents=[],
            response_metadata={},
        )

        # Run graph
        result = await self.graph.ainvoke(initial_state, {"tool_context": tool_context})

        # Format output
        return {
            "answer": result["final_answer"],
            "route": result.get("route_decision"),
            "metadata": result.get("response_metadata", {}),
            "retrieval_contexts": result.get("retrieval_contexts", []),
            "cited_documents": result.get("cited_documents", []),
            "iterations": result.get("iteration_count", 0),
        }
