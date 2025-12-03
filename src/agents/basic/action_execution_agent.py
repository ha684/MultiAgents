# src/agents/basic/action_execution_agent.py
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)

from src.agents.basic.base import BaseAgent
from src.agents.prompts.agent_prompts import PromptTemplates
from src.agents.shared.registry import SubgraphRegistry
from src.agents.tools.server.mcp_retrieve_tools import think
from src.core.config.llm_config import SupportedLLMProviders
from src.utils import get_current_time, parse_response
from src.utils.logger_conf import logger


class ActionExecutionAgent(BaseAgent):
    """
    Action Execution Agent - Execute the action decided by Phase Agent.

    Hai modes:
    1. action="reason_only" → Generate reasoning (deep analysis)
    2. action="use_tool" → Select subgraph and generate query
    """

    def __init__(self, provider: SupportedLLMProviders = "nxchat"):
        super().__init__(provider)

    async def ainvoke(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        Execute action based on next_action.

        If action="reason_only":
            Returns: {"reasoning": str, "subgraph": None, "query": None}

        If action="use_tool":
            Returns: {"subgraph": str, "query": str, "reasoning": None}

        IMPORTANT: For use_tool mode, we intentionally DO NOT include accumulated_context,
        learnings, or missing_aspects to prevent hallucination from polluted context.
        The phase_title is the ONLY source of truth for what to do.
        """
        action = state.get("next_action", "use_tool")
        phase_title = state.get("phase_title", "")
        execution_history = state.get("execution_history", [])

        history_section = ""
        if execution_history:
            recent_history = execution_history[-3:]
            history_text = "\n".join(
                [
                    f"  [{ex.get('iteration')}] {ex.get('subgraph')} - {ex.get('status')}: {ex.get('query', '')[:50]}"
                    + (
                        f" (Error: {ex.get('error')[:30]})"
                        if ex.get("status") == "failed"
                        else ""
                    )
                    for ex in recent_history
                ]
            )
            history_section = (
                f"Previous Attempts (avoid repeating failed ones):\n{history_text}"
            )

        if action == "reason_only":
            knowledge = state.get("accumulated_context", "")
            learnings = state.get("learnings", [])
            missing_aspects = state.get("missing_aspects", "")

            system_prompt = PromptTemplates.REASONING_EXECUTION_PROMPT
            context_parts = [
                knowledge,
                learnings,
                missing_aspects,
            ]
        else:  # use_tool
            system_prompt = PromptTemplates.TOOL_EXECUTION_PROMPT

            active_map = SubgraphRegistry.resolve_active(
                allow=state.get("subgraph_policy", {}).get("allow"),
                block=state.get("subgraph_policy", {}).get("block"),
                extras=state.get("subgraph_policy", {}).get("extras"),
            )
            subgraph_definitions = SubgraphRegistry.generate_routing_prompt(active_map)
            context_parts = [
                subgraph_definitions,
                history_section,
            ]

        context_content = "\n\n".join(filter(None, context_parts))

        messages: list[BaseMessage] = [
            SystemMessage(content=get_current_time() + system_prompt),
            AIMessage(content=context_content),
            HumanMessage(content=f"Phase Title:\n{phase_title}"),
        ]

        if action == "reason_only":
            result = await self.simple_llm_call(
                messages=messages,
                error_context=f"ActionExecutionAgent (reason_only) for action={action}",
            )
            result = parse_action_execution_result(result.content)
        else:
            result = await self.iterative_llm_call_structured(
                messages=messages,
                llm_with_tools=self.thinking_llm,
                available_tools={"think": think},
                max_iterations=3,
                parse_fn=parse_action_execution_result,
                retry_prompt=f"Please provide the execution result in the correct JSON format for action={action}",
            )

        result["action"] = action

        logger.info(
            f"[ActionExecution] Action={action}, Result={result.get('reasoning' if action == 'reason_only' else 'subgraph', 'N/A')[:100]}..."
        )

        return result


def parse_action_execution_result(content: str) -> dict[str, Any] | str:
    """Parse action execution result from content"""
    try:
        parsed = parse_response(content)
        if parsed is None:
            return content

        return parsed
    except Exception as e:
        logger.error(f"Error parsing action execution result: {e}")
        return content
