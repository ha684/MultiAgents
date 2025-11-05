# src/agents/basic/router_agent.py

import textwrap
from typing import List, Optional

from langchain_core.messages import BaseMessage
from langchain_core.messages import get_buffer_string
from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.basic.base import BaseAgent
from src.domain.entities.state import OrchestratorState
from src.domain.schemas.graph import RouteDecision
from src.agents.prompts.agent_prompts import PromptTemplates
from src.agents.shared.registry import SubgraphRegistry
from src.agents.tools.server.mcp_retrieve_tools import think
from src.core.config.llm_config import SupportedLLMProviders
from src.utils import parse_response
from src.utils.logger_conf import logger


class RouterAgent(BaseAgent):
    def __init__(self, provider: SupportedLLMProviders = "nxchat"):
        super().__init__(provider)

    async def ainvoke(self, state: OrchestratorState) -> Optional[RouteDecision]:
        conversation = state["conversation"]

        policy = state.get("subgraph_policy", {})

        active_map = SubgraphRegistry.resolve_active(
            allow=policy.get("allow"),
            block=policy.get("block"),
            extras=policy.get("extras"),
        )

        state["active_subgraphs"] = list(active_map.keys())
        subgraph_definitions = SubgraphRegistry.definitions_from_map(active_map)

        execution_history = state.get("execution_history", [])

        subgraph_context = "\n\n".join(
            [
                f"**{tool['name']}**:\n{tool['description']}"
                for tool in subgraph_definitions
            ]
        )

        history_context = ""
        if execution_history:
            history_context = "\n\n**Previous attempts:**\n" + "\n".join(
                [
                    f"- {h['subgraph']}: {h.get('error', 'No result')}"
                    for h in execution_history
                ]
            )

        max_iterations = 3
        conversation_context = get_buffer_string(conversation)

        system_prompt = SystemMessage(content=PromptTemplates.ROUTER_PROMPT)
        context_message = HumanMessage(
            content=textwrap.dedent(
                f"""<available_subgraphs>
                {subgraph_context}
                </available_subgraphs>

                <execution_history>
                {history_context if history_context else "No previous attempts"}
                </execution_history>

                <conversation_context>
                {conversation_context if conversation_context else "No previous conversation"}
                </conversation_context>

                <current_query>
                {conversation[-1].content}
                </current_query>

                Analyze the query and select the most appropriate subgraph route.
                """
            )
        )
        messages: List[BaseMessage] = [system_prompt, context_message]

        router_llm = self.thinking_llm

        response = await self.iterative_llm_call_structured(
            messages=messages,
            llm_with_tools=router_llm,
            available_tools={"think": think},
            max_iterations=max_iterations,
            parse_fn=parse_route_decision,
            retry_prompt=(
                "Please provide the route decision in correct JSON format with 'route' key "
                "matching one of the available subgraph names."
            ),
        )

        return response


def parse_route_decision(content: str) -> Optional[RouteDecision]:
    """Parse route decision from content"""
    try:
        parsed = parse_response(content)
        if parsed is None:
            return None
        return RouteDecision(**parsed)
    except Exception as e:
        logger.error(f"Error parsing route decision: {e}")
        return None
