# src/agents/basic/router_agent.py

from typing import List, Optional

from langchain_core.messages import BaseMessage
from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.basic.base import BaseAgent
from src.agents.graph.state import OrchestratorState, ReflectionResult
from src.agents.shared.prompts import PromptTemplates
from src.agents.tools.server.mcp_retrieve_tools import think
from src.core.config.llm_config import SupportedLLMProviders
from src.utils import format_context_for_response, parse_response
from src.utils.logger_conf import logger


class ReflectionAgent(BaseAgent):
    def __init__(self, provider: SupportedLLMProviders = "nxchat"):
        super().__init__(provider)

    async def ainvoke(self, state: OrchestratorState) -> Optional[ReflectionResult]:
        current_iteration = state.get("current_iteration", 1)
        max_iterations = state.get("max_iterations")
        route = state.get("route_decision")
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
                accumulated_context = format_context_for_response(
                    state.get("cited_documents") or []
                )

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

        return reflection_result


def parse_reflection_result(content: str) -> Optional[ReflectionResult]:
    """Parse reflection result from content"""
    try:
        parsed = parse_response(content)
        if parsed is None:
            return None
        return ReflectionResult(**parsed)
    except Exception as e:
        logger.error(f"Error parsing reflection result: {e}")
        return None
