# src/agents/basic/action_execution_agent.py
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
from src.agents.shared.registry import SubgraphRegistry
from src.agents.tools.server.mcp_retrieve_tools import think
from src.core.config.llm_config import SupportedLLMProviders
from src.utils import parse_response
from src.utils.logger_conf import logger


class ActionExecutionAgent(BaseAgent):
    """
    Action Execution Agent - Thực thi action đã được quyết định bởi Phase Agent.

    Hai modes:
    1. action="reason_only" → Generate reasoning (deep analysis)
    2. action="use_tool" → Select subgraph và generate query
    """

    def __init__(self, provider: SupportedLLMProviders = "nxchat"):
        super().__init__(provider)

    async def ainvoke(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        Execute action based on next_action.

        If action="reason_only":
            Returns: {"reasoning": str, "subgraph": null, "query": null}

        If action="use_tool":
            Returns: {"subgraph": str, "query": str, "reasoning": null}
        """
        action = state.get("next_action", "use_tool")
        phase_title = state.get("phase_title", "")
        learnings = state.get("learnings", [])
        knowledge = state.get("accumulated_context", "")
        execution_history = state.get("execution_history", [])
        missing_aspects = state.get("_missing_aspects", "")

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

        # Select appropriate prompt based on action
        if action == "reason_only":
            system_prompt = PromptTemplates.REASONING_EXECUTION_PROMPT
            context_parts = [
                f"Phase: {phase_title}",
                knowledge_section,
                learnings_section,
                missing_section,
            ]
        else:  # use_tool
            system_prompt = PromptTemplates.TOOL_EXECUTION_PROMPT

            # Get available subgraphs
            active_map = SubgraphRegistry.resolve_active(
                allow=state.get("subgraph_policy", {}).get("allow"),
                block=state.get("subgraph_policy", {}).get("block"),
                extras=state.get("subgraph_policy", {}).get("extras"),
            )
            subgraph_definitions = SubgraphRegistry.generate_routing_prompt(active_map)

            context_parts = [
                f"Phase: {phase_title}",
                subgraph_definitions,
                knowledge_section,
                learnings_section,
                history_section,
                missing_section,
            ]

        context_content = "\n\n".join(filter(None, context_parts))

        messages: list[BaseMessage] = [
            SystemMessage(content=system_prompt),
            AIMessage(content=context_content),
            HumanMessage(content=f"User Query:\n{conversation_text}"),
        ]

        result = await self.iterative_llm_call_structured(
            messages=messages,
            llm_with_tools=self.thinking_llm,
            available_tools={"think": think},
            max_iterations=3,
            parse_fn=parse_action_execution_result,
            retry_prompt=f"Please provide the execution result in the correct JSON format for action={action}",
        )

        # Add action to result for validation
        result["action"] = action

        logger.info(
            f"[ActionExecution] Action={action}, Result={result.get('reasoning' if action == 'reason_only' else 'subgraph', 'N/A')[:100]}..."
        )

        return result


def parse_action_execution_result(content: str) -> dict[str, Any] | None:
    """Parse action execution result from content"""
    try:
        parsed = parse_response(content)
        if parsed is None:
            return None

        # Note: We validate based on action in the agent's ainvoke method
        # because we need to know the action type to validate properly
        return parsed
    except Exception as e:
        logger.error(f"Error parsing action execution result: {e}")
        return None
