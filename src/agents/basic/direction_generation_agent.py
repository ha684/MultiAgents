# src/agents/basic/router_agent.py
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


class DirectionGenerationAgent(BaseAgent):
    def __init__(self, provider: SupportedLLMProviders = "nxchat"):
        super().__init__(provider)

    async def ainvoke(self, state: dict[str, Any]) -> dict[str, Any]:
        learnings = state.get("learnings", [])
        knowledge = state.get("accumulated_context", "")
        execution_history = state.get("execution_history", [])

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

        missing_aspects = state.get("_missing_aspects", "")
        missing_section = (
            f"Missing Aspects:\n{missing_aspects}" if missing_aspects else ""
        )

        active_map = SubgraphRegistry.resolve_active(
            allow=state.get("subgraph_policy", {}).get("allow"),
            block=state.get("subgraph_policy", {}).get("block"),
            extras=state.get("subgraph_policy", {}).get("extras"),
        )
        subgraph_definitions = SubgraphRegistry.generate_routing_prompt(active_map)

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

        messages: list[BaseMessage] = [
            SystemMessage(content=PromptTemplates.DIRECTION_GENERATION_PROMPT),
            AIMessage(
                content="\n\n".join(
                    filter(
                        None,
                        [
                            subgraph_definitions,
                            knowledge_section,
                            learnings_section,
                            history_section,
                            missing_section,
                        ],
                    )
                )
            ),
            HumanMessage(content=f"Conversation:\n{conversation_text}"),
        ]

        reflection_result = await self.iterative_llm_call_structured(
            messages=messages,
            llm_with_tools=self.thinking_llm,
            available_tools={"think": think},
            max_iterations=3,
            parse_fn=parse_reflection_result,
            retry_prompt="Please provide the reflection in the correct JSON format.",
        )
        return reflection_result


def parse_reflection_result(content: str) -> dict[str, Any] | None:
    """Parse reflection result from content"""
    try:
        parsed = parse_response(content)
        if parsed is None:
            return None
        return parsed
    except Exception as e:
        logger.error(f"Error parsing reflection result: {e}")
        return None
