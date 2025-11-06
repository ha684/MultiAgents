# src/agents/basic/dynamic_query_agent.py
import json
from typing import Dict, List, Optional

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from src.agents.basic.base import BaseAgent
from src.domain.entities.state import ResearchState
from src.utils.decorators import singleton
from src.utils.logger_conf import logger
from src.agents.prompts.agent_prompts import PromptTemplates
from src.agents.tools.server.mcp_retrieve_tools import think
from src.utils import parse_response
from src.domain.schemas.graph import DynamicQueriesSchema


@singleton
class DynamicQueryAgent(BaseAgent):
    """Agent responsible for generating dynamic queries."""

    def __init__(self):
        super().__init__()
        logger.info("Dynamic Query Agent initialized successfully.")

    async def ainvoke(self, state: ResearchState) -> Dict:
        """
        Generates dynamic queries.
        """
        max_iterations = 3
        verification = state["verification_result"]

        if not verification or not verification.get("missing_aspects"):
            logger.warning(
                "[DynamicQueryGenerator] No missing aspects identified. Skipping query generation."
            )
            return {
                "pending_queries": [],
                "cited_documents": state.get("cited_documents", []),
                "accumulated_knowledge": state.get("accumulated_knowledge", ""),
            }

        missing_aspects = verification["missing_aspects"]

        search_history = []
        for search_result in state.get("all_search_history", []):
            search_history.append(
                {
                    "query": search_result["query"],
                    "search_type": search_result["search_type"],
                }
            )

        search_history_str = (
            json.dumps(search_history, ensure_ascii=False)
            if search_history
            else "No previous searches"
        )

        reflection = state.get(
            "reflection_result", {"critique": "N/A", "next_steps": "N/A"}
        )
        reflection_str = f"Critique: {reflection['critique']}\nSuggested Next Steps: {reflection['next_steps']}"

        prompt_input = PromptTemplates.DYNAMIC_QUERY_GENERATOR_HUMAN_PROMPT.format(
            original_query=state["contextualized_query"],
            accumulated_knowledge=state["accumulated_knowledge"],
            missing_aspects=json.dumps(missing_aspects, ensure_ascii=False),
            search_history=search_history_str,
            reflection=reflection_str,
        )

        messages: List[BaseMessage] = [
            SystemMessage(content=PromptTemplates.DYNAMIC_QUERY_GENERATOR_PROMPT),
            HumanMessage(content=prompt_input),
        ]

        dynamic_query_generator_llm = self.thinking_llm
        dynamic_query_generator_dict = await self.iterative_llm_call_structured(
            messages=messages,
            llm_with_tools=dynamic_query_generator_llm,
            available_tools={"think": think},
            max_iterations=max_iterations,
            parse_fn=parse_dynamic_query_generator_response,
            retry_prompt="Please provide the dynamic query generator result in correct JSON format.",
        )

        return dynamic_query_generator_dict


def parse_dynamic_query_generator_response(
    content: str,
) -> Optional[DynamicQueriesSchema]:
    """Parse dynamic query generator response"""
    try:
        parsed = parse_response(content)
        if not parsed:
            logger.warning(
                "[Parser] Failed to parse dynamic query generator response (null result)."
            )
            return content
        response = DynamicQueriesSchema(**parsed)
        dumped = response.model_dump()
        return dumped
    except Exception as e:
        logger.error(
            f"[Parser] Error parsing dynamic query generator response: {e}",
            exc_info=True,
        )
        return content
