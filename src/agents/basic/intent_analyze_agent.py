from typing import Dict, Any

from langchain_core.messages import SystemMessage

from src.agents.graph.state import OrchestratorState
from src.agents.com.registry import registry
from src.utils import parse_response
from src.agents.basic.base import BaseAgent

INTENT_ANALYZE_PROMPT_TEMPLATE = """
"""


class IntentAnalyzeAgent(BaseAgent):
    """
    Analyzes query and conversation context to create an execution plan.
    Không quyết định cứng nhắc - tạo ra flexible plan.
    """

    def __init__(self, llm):
        self.llm = llm

    async def ainvoke(self, state: OrchestratorState) -> Dict[str, Any]:
        """Analyze intent and create execution plan"""

        system_prompt = f"""You are an intent understanding specialist.

Available execution strategies:
{self._format_available_subgraphs()}

Your task:
1. Understand the user's query and conversation context
2. Determine primary strategy and potential fallbacks
3. Identify any clarifications needed

Output a JSON plan:
{{
    "primary_strategy": "subgraph_name or 'direct_response'",
    "fallback_strategies": ["backup_subgraph1", "backup_subgraph2"],
    "reasoning": "why you chose this approach",
    "needs_clarification": false
}}
"""

        messages = [SystemMessage(content=system_prompt), *state["conversation"]]

        response = await self.simple_llm_call(messages, self.llm)
        plan = parse_response(str(response.content))

        return {
            "execution_plan": plan,
            "execution_status": "awaiting_user"
            if plan.get("needs_clarification")
            else "executing",
            "agent_thoughts": [plan["reasoning"]],
        }

    def _format_available_subgraphs(self) -> str:
        """Format subgraph registry for LLM"""
        tools = registry.get_definitions()
        return "\n\n".join(
            f"**{tool['name']}**\n{tool['description']}" for tool in tools
        )
