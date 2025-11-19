# src/agents/basic/verification_agent.py
from typing import Any, Dict, List, Optional

from langchain_core.messages import (
    BaseMessage,
    AIMessage,
    HumanMessage,
    SystemMessage,
    get_buffer_string,
)

from src.agents.basic.base import BaseAgent
from src.agents.prompts.agent_prompts import PromptTemplates
from src.agents.tools.server.mcp_retrieve_tools import think
from src.core.config.llm_config import SupportedLLMProviders
from src.domain.entities.state import ThinkingState
from src.domain.schemas.graph import VerificationSchema
from src.utils import parse_response
from src.utils.decorators import singleton
from src.utils.logger_conf import logger


@singleton
class VerificationAgent(BaseAgent):
    """Agent responsible for verifying information from relevant documents."""

    def __init__(self, provider: SupportedLLMProviders = "nxchat"):
        super().__init__(provider)
        logger.info("Verification Agent initialized successfully.")

    async def ainvoke(self, state: ThinkingState) -> Dict[str, Any]:
        """
        Verifies information from relevant documents.
        """
        max_iterations = 3
        conversation_text = get_buffer_string(state["conversation"])

        total_context = f"Accumulated context:\n{state.get('accumulated_context', '') + '\n\n' + state.get('internal_reasoning', '')}"
        messages: List[BaseMessage] = [
            SystemMessage(content=PromptTemplates.VERIFICATION_PROMPT),
            AIMessage(content=total_context),
            HumanMessage(content=f"Conversation: {conversation_text}"),
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


def parse_verification_response(content: str) -> Optional[VerificationSchema]:
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
