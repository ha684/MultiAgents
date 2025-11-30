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

        Args:
            state: Current state with conversation, context, etc.
            mode: "thinking" (iterative, reasoning-first) or "normal" (single-shot, tool-focused)

        Returns:
            {
                "phase_title": str,     # Example: "Looking up renewable energy reports"
                "next_action": str,     # Example: "reason_only" or "use_tool"
            }
        """
        # Select prompt based on mode
        if mode == "normal":
            system_prompt = PromptTemplates.PHASE_PLANNING_NORMAL_PROMPT
        else:
            system_prompt = PromptTemplates.PHASE_PLANNING_PROMPT

        learnings = state.get("learnings", [])
        knowledge = state.get("accumulated_context", "")
        execution_history = state.get("execution_history", [])
        missing_aspects = state.get("_missing_aspects", "")
        iteration_count = state.get("iteration_count", 0)

        # Build iteration progress section
        iteration_section = f"## Current Progress: Iteration {iteration_count}"

        # Add last execution result info for context
        last_execution_info = ""
        if execution_history:
            last_ex = execution_history[-1]
            last_status = last_ex.get("status", "unknown")
            last_subgraph = last_ex.get("subgraph", "unknown")
            if last_status == "success":
                result_count = last_ex.get("result_count", 0)
                last_execution_info = (
                    f"Last Action: {last_subgraph} - SUCCESS ({result_count} results)"
                )
            else:
                error = last_ex.get("error", "Unknown error")
                last_execution_info = f"Last Action: {last_subgraph} - FAILED ({error})"

        history_section = ""
        if execution_history:
            recent_history = execution_history[-5:]
            history_text = "\n".join(
                [
                    f"  [{ex.get('iteration')}] {ex.get('subgraph')} - {ex.get('status')}: {ex.get('query', '')[:60]}..."
                    + (
                        f" (Error: {ex.get('error')})"
                        if ex.get("status") == "failed"
                        else ""
                    )
                    for ex in recent_history
                ]
            )
            history_section = f"Execution History:\n{history_text}"

        if isinstance(missing_aspects, list):
            missing_aspects = "\n".join(missing_aspects)

        missing_section = (
            f"Missing Aspects:\n{missing_aspects}" if missing_aspects else ""
        )

        knowledge_section = ""
        if knowledge:
            truncated = len(knowledge) > 3000
            prefix = "(Showing most recent ~3000 chars)\n" if truncated else ""
            knowledge_section = f"Accumulated Knowledge:\n{prefix}{knowledge[-3000:]}"

        learnings_text = (
            "\n".join(f"- {learning}" for learning in learnings[-3:])
            if learnings
            else "None yet"
        )
        learnings_section = f"Previous Learnings:\n{learnings_text}"

        conversation_text = get_buffer_string(state["conversation"])
        current_time = f"The current time is {get_current_time()}, remember this."
        previous_phase = state.get("phase_title", "")
        previous_phase_section = (
            f"Previous Phase: {previous_phase}" if previous_phase else ""
        )

        context_parts = [
            iteration_section,
            previous_phase_section,
            last_execution_info,
            knowledge_section,
            learnings_section,
            history_section,
            missing_section,
        ]
        context_content = "\n\n".join(filter(None, context_parts))

        messages: list[BaseMessage] = [
            SystemMessage(content=current_time + system_prompt),
            AIMessage(content=context_content),
            HumanMessage(content=f"Conversation:\n{conversation_text}"),
        ]

        phase_result = await self.iterative_llm_call_structured(
            messages=messages,
            llm_with_tools=self.thinking_llm,
            available_tools={"think": think},
            max_iterations=3,
            parse_fn=parse_phase_result,
            retry_prompt='Please provide the phase decision in the correct JSON format: {"phase_title": "...", "next_action": "reason_only" or "use_tool"}',
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
