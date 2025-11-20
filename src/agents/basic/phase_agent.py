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
from src.core.config.llm_config import SupportedLLMProviders
from src.utils import parse_response
from src.utils.logger_conf import logger


class PhaseAgent(BaseAgent):
    """
    Phase Agent - Quyết định phase tiếp theo trong quá trình research.

    Giống như ChatGPT, agent này:
    - Phân tích tình hình hiện tại (missing aspects, learnings, etc.)
    - Quyết định phase title (VD: "Looking up renewable energy reports")
    - Quyết định next action: "reason_only" hoặc "use_tool"
    """

    def __init__(self, provider: SupportedLLMProviders = "nxchat"):
        super().__init__(provider)

    async def ainvoke(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        Generate phase title and decide next action type.

        Returns:
            {
                "phase_title": str,     # VD: "Looking up renewable energy reports"
                "next_action": str,     # "reason_only" hoặc "use_tool"
            }
        """
        learnings = state.get("learnings", [])
        knowledge = state.get("accumulated_context", "")
        execution_history = state.get("execution_history", [])
        missing_aspects = state.get("_missing_aspects", "")
        iteration_count = state.get("iteration_count", 0)

        # Build execution history section
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

        # Build missing aspects section
        missing_section = (
            f"Missing Aspects:\n{missing_aspects}" if missing_aspects else ""
        )

        # Build knowledge section
        knowledge_section = (
            f"Accumulated Knowledge:\n{knowledge[-3000:]}" if knowledge else ""
        )

        # Build learnings section
        learnings_text = (
            "\n".join(f"- {learning}" for learning in learnings[-3:])
            if learnings
            else "None yet"
        )
        learnings_section = f"Previous Learnings:\n{learnings_text}"

        # Build conversation
        conversation_text = get_buffer_string(state["conversation"])

        # Build context message
        context_parts = [
            f"Current Iteration: {iteration_count}",
            knowledge_section,
            learnings_section,
            history_section,
            missing_section,
        ]
        context_content = "\n\n".join(filter(None, context_parts))

        messages: list[BaseMessage] = [
            SystemMessage(content=PromptTemplates.PHASE_PLANNING_PROMPT),
            AIMessage(content=context_content),
            HumanMessage(content=f"User Query:\n{conversation_text}"),
        ]

        phase_result = await self.iterative_llm_call_structured(
            messages=messages,
            llm_with_tools=self.thinking_llm,
            available_tools={"think": think},
            max_iterations=3,
            parse_fn=parse_phase_result,
            retry_prompt='Please provide the phase decision in the correct JSON format: {"phase_title": "...", "next_action": "reason_only" or "use_tool"}',
        )

        logger.info(
            f"[Phase] Iter={iteration_count}, Title='{phase_result.get('phase_title', 'N/A')}', Action={phase_result.get('next_action', 'N/A')}"
        )

        return phase_result


def parse_phase_result(content: str) -> dict[str, Any] | None:
    """Parse phase result from content"""
    try:
        parsed = parse_response(content)
        if parsed is None:
            return None

        # Validate required fields
        if "phase_title" not in parsed or "next_action" not in parsed:
            logger.error("Missing required fields: phase_title or next_action")
            return None

        # Validate next_action value
        if parsed["next_action"] not in ["reason_only", "use_tool"]:
            logger.error(
                f"Invalid next_action: {parsed['next_action']}, must be 'reason_only' or 'use_tool'"
            )
            return None

        return parsed
    except Exception as e:
        logger.error(f"Error parsing phase result: {e}")
        return None
