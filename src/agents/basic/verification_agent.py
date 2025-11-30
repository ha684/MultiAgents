# src/agents/basic/verification_agent.py
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
from src.domain.entities.state import ThinkingState
from src.domain.schemas.graph import VerificationSchema
from src.utils import get_current_time, parse_response
from src.utils.decorators import singleton
from src.utils.logger_conf import logger


@singleton
class VerificationAgent(BaseAgent):
    """Agent responsible for verifying information from relevant documents."""

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
        logger.info("Verification Agent initialized successfully.")

    async def ainvoke(self, state: ThinkingState) -> dict[str, Any]:
        """
        Verifies information from relevant documents.
        """
        max_iterations = 3
        conversation_text = get_buffer_string(state["conversation"])
        current_time = f"The current time is {get_current_time()}, remember this."
        internal_reasoning = state.get("_internal_reasoning", "").strip()
        accumulated_context = state.get("accumulated_context", "").strip()

        execution_history = state.get("execution_history", [])
        successful_executions = [
            ex for ex in execution_history if ex.get("status") == "success"
        ]

        knowledge_summary = self._build_knowledge_summary(
            internal_reasoning=internal_reasoning,
            accumulated_context=accumulated_context,
            execution_history=successful_executions,
            iteration_count=state.get("iteration_count", 0),
        )

        messages: list[BaseMessage] = [
            SystemMessage(content=current_time + PromptTemplates.VERIFICATION_PROMPT),
            AIMessage(content=knowledge_summary),
            HumanMessage(content=f"Conversation:\n{conversation_text}"),
        ]

        verification_llm = self.thinking_llm
        verification_dict = await self.iterative_llm_call_structured(
            messages=messages,
            llm_with_tools=verification_llm,
            available_tools={"think": think},
            max_iterations=max_iterations,
            parse_fn=parse_verification_response,
            retry_prompt="Please provide the verification result in correct JSON format.",
        )

        return verification_dict

    def _build_knowledge_summary(
        self,
        internal_reasoning: str,
        accumulated_context: str,
        execution_history: list,
        iteration_count: int,
    ) -> str:
        """
        Build a clear summary of what knowledge we have and where it came from.
        This helps verification agent understand the SOURCE of information.
        """
        summary_parts = []

        summary_parts.append(f"## Research Progress: Iteration {iteration_count}")
        summary_parts.append("")

        if internal_reasoning:
            summary_parts.append("### Internal Reasoning (No External Sources)")
            summary_parts.append("- Generated from your own knowledge")
            summary_parts.append("")
            summary_parts.append("Content:")
            summary_parts.append(internal_reasoning)
            summary_parts.append("")

        if accumulated_context:
            summary_parts.append("### External Sources (From Tool Executions)")

            if execution_history:
                summary_parts.append(
                    f"- Total successful searches: {len(execution_history)}"
                )
                summary_parts.append("- Tools used:")
                for ex in execution_history:
                    subgraph = ex.get("subgraph", "unknown")
                    query = ex.get("query", "")[:60]
                    summary_parts.append(f'  • {subgraph}: "{query}"')
            else:
                summary_parts.append("- No external searches completed yet")

            summary_parts.append("")
            summary_parts.append("Content:")
            summary_parts.append(accumulated_context)
        else:
            summary_parts.append("### External Sources")
            summary_parts.append("- No external sources gathered yet")
            summary_parts.append(
                "- All current knowledge is from internal reasoning only"
            )

        return "\n".join(summary_parts)


def parse_verification_response(content: str) -> VerificationSchema | None:
    """Parse verification response"""
    try:
        parsed = parse_response(content)
        if not parsed:
            logger.warning(
                "[Parser] Failed to parse verification response (null result)."
            )
            return content
        response = VerificationSchema(**parsed)
        dumped = response.model_dump()
        return dumped
    except Exception as e:
        logger.error(
            f"[Parser] Error parsing verification response: {e}", exc_info=True
        )
        return content
