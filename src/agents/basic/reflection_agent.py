# src/agents/basic/router_agent.py
from typing import Any, Dict, List, Optional

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

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

        active_map = SubgraphRegistry.resolve_active(
            allow=state.get("subgraph_policy", {}).get("allow"),
            block=state.get("subgraph_policy", {}).get("block"),
            extras=state.get("subgraph_policy", {}).get("extras"),
        )

        prompt_input = PromptTemplates.REFLECTION_HUMAN_PROMPT.format(
            original_query=state["contextualized_query"],
            learnings="\n".join(f"- {learning}" for learning in learnings[-3:])
            if learnings
            else "None yet",
            knowledge=knowledge[-3000:] if knowledge else "None yet",
            subgraph_definitions=SubgraphRegistry.generate_routing_prompt(active_map),
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
