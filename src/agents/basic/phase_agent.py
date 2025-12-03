# src/agents/basic/phase_agent.py
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    get_buffer_string,
)

from src.agents.basic.base import BaseAgent
from src.agents.prompts.agent_prompts import PromptTemplates
from src.agents.tools.server.mcp_retrieve_tools import think
from src.core.config.llm_config import LLMModelConfigs
from src.core.config.settings import settings
from src.utils import get_current_time, parse_response
from src.utils.logger_conf import logger


class PhaseAgent(BaseAgent):
    """
    Phase Agent - Determines the next phase in the research process.

    Supports two modes:
    1. "thinking" (default): Iterative research with reasoning preference
    2. "normal": Single-shot execution with direct tool selection

    Like ChatGPT, this agent:
    - Analyzes the current situation (missing aspects, learnings, etc.)
    - Decides on the phase title (e.g., "Looking up renewable energy reports")
    - Decides the next action: "reason_only" or "use_tool"
    """

    def __init__(self):
        super().__init__(
            provider="nxchat",
            config=LLMModelConfigs(
                model="nxchat-internal",
                base_url=settings.ntqai_base_url,
                api_key=settings.ntqai_api_key,
                temperature=0.0,
            ),
        )

    async def ainvoke(
        self, state: dict[str, Any], mode: str = "thinking"
    ) -> dict[str, Any]:
        """
        Generate phase title and decide next action type.
        """
        if mode == "normal":
            system_prompt = PromptTemplates.PHASE_PLANNING_NORMAL_PROMPT
        else:
            system_prompt = PromptTemplates.PHASE_PLANNING_PROMPT

        iteration_count = state.get("iteration_count", 0)
        missing_aspects = state.get("_missing_aspects", "")
        execution_history = state.get("execution_history", [])
        conversation_text = get_buffer_string(state["conversation"])

        messages: list[BaseMessage] = [
            SystemMessage(content=get_current_time() + system_prompt),
            AIMessage(
                content=f"<research_state>\n{iteration_count} {execution_history} {missing_aspects}\n</research_state>"
            ),
            HumanMessage(
                content=f"<original_conversation>\n{conversation_text}\n</original_conversation>"
            ),
        ]

        phase_result = await self.iterative_llm_call_structured(
            messages=messages,
            llm_with_tools=self.thinking_llm,
            available_tools={"think": think},
            max_iterations=3,
            parse_fn=parse_phase_result,
            retry_prompt='Return JSON: {"phase_title": "...", "next_action": "reason_only"|"use_tool"}',
        )

        return phase_result


def parse_phase_result(content: str) -> dict[str, Any] | str:
    """Parse phase result from content"""
    if isinstance(content, dict):
        return content
    try:
        parsed = parse_response(content)
        if parsed is None:
            return content

        return parsed
    except Exception as e:
        logger.error(f"Error parsing phase result: {e}")
        return content
