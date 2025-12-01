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
        previous_phase = state.get("phase_title", "")
        missing_aspects = state.get("_missing_aspects", "")
        execution_history = state.get("execution_history", [])
        knowledge = state.get("accumulated_context", "")
        learnings = state.get("learnings", [])

        state_summary = f"**Iteration {iteration_count}**"

        if previous_phase:
            state_summary += f"\n**Previous Phase**: {previous_phase}"
            state_summary += f"\nYour next phase title MUST be meaningfully different from '{previous_phase}'"

        if execution_history:
            last_ex = execution_history[-1]
            last_status = last_ex.get("status", "unknown")
            last_subgraph = last_ex.get("subgraph", "unknown")
            last_query = last_ex.get("query", "")[:80]

            if last_status == "success":
                result_count = last_ex.get("result_count", 0)
                state_summary += f"\n**Last Action**: ✓ {last_subgraph} succeeded ({result_count} results)"
                state_summary += f"\n   Query: '{last_query}'"
            else:
                error = last_ex.get("error", "Unknown error")
                state_summary += f"\n**Last Action**: ✗ {last_subgraph} FAILED"
                state_summary += f"\n   Error: {error}"
                state_summary += f"\n   Query: '{last_query}'"

                recent_failures = [
                    ex for ex in execution_history[-3:] if ex.get("status") == "failed"
                ]
                if len(recent_failures) >= 2:
                    state_summary += "\nMultiple recent failures - consider reasoning with available data"

        if missing_aspects:
            if isinstance(missing_aspects, list):
                missing_text = "\n".join(f"- {aspect}" for aspect in missing_aspects)
            else:
                missing_text = missing_aspects
            state_summary += f"\n\n**Current Gap**:\n{missing_text}"

        knowledge_length = len(knowledge)
        if knowledge_length > 0:
            state_summary += f"\n\n**Accumulated Knowledge**: {knowledge_length} chars"
            if knowledge_length > 500:
                preview = knowledge[:200] + "\n...\n" + knowledge[-200:]
            else:
                preview = knowledge
            state_summary += f"\nPreview:\n{preview}"
        else:
            state_summary += (
                "\n\n**Accumulated Knowledge**: Empty (need data or reasoning)"
            )

        if len(execution_history) >= 3:
            recent_3 = execution_history[-3:]
            pattern = " → ".join(
                [
                    f"{ex.get('subgraph', 'reason')}({'✓' if ex.get('status') == 'success' else '✗'})"
                    for ex in recent_3
                ]
            )
            state_summary += f"\n\n**Recent Pattern**: {pattern}"

        if learnings:
            recent_learnings = learnings[-2:]
            learnings_text = "\n".join(f"- {l}" for l in recent_learnings)
            state_summary += f"\n\n**Recent Learnings**:\n{learnings_text}"

        conversation_text = get_buffer_string(state["conversation"])

        messages: list[BaseMessage] = [
            SystemMessage(content=get_current_time() + system_prompt),
            AIMessage(content=f"<research_state>\n{state_summary}\n</research_state>"),
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
