# src/agents/basic/planner_agent.py
from typing import Dict, List, Optional

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from src.agents.basic.base import BaseAgent
from src.domain.entities.state import OrchestratorState
from src.utils.decorators import singleton
from src.utils.logger_conf import logger
from src.agents.prompts.agent_prompts import PromptTemplates
from src.agents.tools.server.mcp_retrieve_tools import think
from src.utils import parse_response
from src.domain.schemas.graph import SearchPlanSchema


@singleton
class PlannerAgent(BaseAgent):
    """Agent responsible for planning the research process."""

    def __init__(self):
        super().__init__()
        logger.info("Planner Agent initialized successfully.")

    async def ainvoke(self, state: OrchestratorState) -> Dict:
        """
        Plans the research process.
        """
        max_iterations = 5
        system_prompt = SystemMessage(content=PromptTemplates.QUERY_PLANNER_PROMPT)
        prompt = HumanMessage(
            content=f"Create the plan for the following query: {state['contextualized_query']}"
        )
        messages: List[BaseMessage] = [system_prompt] + [prompt]

        query_planner_llm = self.thinking_llm
        response = await self.iterative_llm_call_structured(
            messages=messages,
            llm_with_tools=query_planner_llm,
            available_tools={"think": think},
            max_iterations=max_iterations,
            parse_fn=parse_planner_response,
            retry_prompt="Please provide the research plan in correct JSON format.",
        )
        return response


def parse_planner_response(content: str) -> Optional[SearchPlanSchema]:
    """Parse planner response"""
    try:
        parsed = parse_response(content)
        if not parsed:
            logger.warning("[Parser] Failed to parse planner response (null result).")
            return content
        response = SearchPlanSchema(**parsed)
        dumped = response.model_dump()
        return dumped
    except Exception as e:
        logger.error(f"[Parser] Error parsing planner response: {e}", exc_info=True)
        return content
