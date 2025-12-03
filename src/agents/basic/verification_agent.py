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
    """Agent responsible for verifying if we can answer the question well."""

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
        Verifies if we should continue researching or synthesize answer now.

        Returns:
            {
                "should_continue": bool,
                "missing_aspects": str,
            }
        """
        max_iterations = 3
        conversation_text = get_buffer_string(state["conversation"])
        iteration_count = state.get("iteration_count", 0)
        consecutive_failures = state.get("consecutive_failures", 0)

        execution_history = state.get("execution_history", [])
        messages: list[BaseMessage] = [
            SystemMessage(
                content=get_current_time() + PromptTemplates.VERIFICATION_PROMPT
            ),
            AIMessage(
                content=iteration_count + " " + execution_history + consecutive_failures
            ),
            HumanMessage(
                content=f"<original_conversation>\n{conversation_text}\n</original_conversation>"
            ),
        ]

        verification_llm = self.thinking_llm
        verification_dict = await self.iterative_llm_call_structured(
            messages=messages,
            llm_with_tools=verification_llm,
            available_tools={"think": think},
            max_iterations=max_iterations,
            parse_fn=parse_verification_response,
            retry_prompt='Return JSON: {"should_continue": true/false, "missing_aspects": "..."}',
        )

        return verification_dict


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
