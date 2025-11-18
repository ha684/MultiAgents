# src/agents/basic/router_agent.py
from typing import Any, Dict, List, Optional

from langchain_core.messages import (
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


class ReflectionAgent(BaseAgent):
    def __init__(self, provider: SupportedLLMProviders = "nxchat"):
        super().__init__(provider)

    async def ainvoke(self, state: Dict[str, Any]) -> Dict[str, Any]:
        learnings = state.get("learnings", [])
        knowledge = state.get("accumulated_knowledge", "")
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
            history_section = f"Execution History:\n{history_text}\n"

        active_map = SubgraphRegistry.resolve_active(
            allow=state.get("subgraph_policy", {}).get("allow"),
            block=state.get("subgraph_policy", {}).get("block"),
            extras=state.get("subgraph_policy", {}).get("extras"),
        )

        missing_aspects = state.get("_missing_aspects", "")
        missing_section = (
            f"Missing Aspects: {missing_aspects}\n" if missing_aspects else ""
        )

        conversation_text = get_buffer_string(state["conversation"])

        prompt_input = PromptTemplates.REFLECTION_HUMAN_PROMPT.format(
            conversation_text=conversation_text,
            learnings="\n".join(f"- {learning}" for learning in learnings[-3:])
            if learnings
            else "None yet",
            knowledge=knowledge[-3000:] if knowledge else "None yet",
            execution_history_section=history_section,
            subgraph_definitions=SubgraphRegistry.generate_routing_prompt(active_map),
            missing_aspects_section=missing_section,
        )

        messages: List[BaseMessage] = [
            SystemMessage(content=PromptTemplates.REFLECTION_PROMPT),
            HumanMessage(content=prompt_input),
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


def parse_reflection_result(content: str) -> Optional[Dict[str, Any]]:
    """Parse reflection result from content"""
    try:
        parsed = parse_response(content)
        if parsed is None:
            return None
        return parsed
    except Exception as e:
        logger.error(f"Error parsing reflection result: {e}")
        return None
