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
    Phase Agent - Determines the next phase in the research process.

    Like ChatGPT, this agent:
    - Analyzes the current situation (missing aspects, learnings, etc.)
    - Decides on the phase title (e.g., "Looking up renewable energy reports")
    - Decides the next action: "reason_only" or "use_tool"
    """

    def __init__(self, provider: SupportedLLMProviders = "nxchat"):
        super().__init__(provider)

    async def ainvoke(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        Generate phase title and decide next action type.

        Returns:
            {
                "phase_title": str,     # Example: "Looking up renewable energy reports"
                "next_action": str,     # Example: "reason_only" or "use_tool"
            }
        """
        learnings = state.get("learnings", [])
        knowledge = state.get("accumulated_context", "")
        execution_history = state.get("execution_history", [])
        missing_aspects = state.get("_missing_aspects", "")

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

        missing_section = (
            f"Missing Aspects:\n{missing_aspects}" if missing_aspects else ""
        )

        knowledge_section = (
            f"Accumulated Knowledge:\n{knowledge[-3000:]}" if knowledge else ""
        )

        learnings_text = (
            "\n".join(f"- {learning}" for learning in learnings[-3:])
            if learnings
            else "None yet"
        )
        learnings_section = f"Previous Learnings:\n{learnings_text}"

        conversation_text = get_buffer_string(state["conversation"])

        context_parts = [
            knowledge_section,
            learnings_section,
            history_section,
            missing_section,
        ]
        context_content = "\n\n".join(filter(None, context_parts))

        messages: list[BaseMessage] = [
            SystemMessage(content=PromptTemplates.PHASE_PLANNING_PROMPT),
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


def parse_phase_result(content: str) -> dict[str, Any] | None:
    """Parse phase result from content"""
    try:
        parsed = parse_response(content)
        if parsed is None:
            return None

        if "phase_title" not in parsed or "next_action" not in parsed:
            logger.error("Missing required fields: phase_title or next_action")
            return None

        if parsed["next_action"] not in ["reason_only", "use_tool"]:
            logger.error(
                f"Invalid next_action: {parsed['next_action']}, must be 'reason_only' or 'use_tool'"
            )
            return None

        return parsed
    except Exception as e:
        logger.error(f"Error parsing phase result: {e}")
        return None
