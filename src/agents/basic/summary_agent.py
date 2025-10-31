# src/agents/basic/summary_agent.py

from typing import List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.messages import get_buffer_string

from src.agents.basic.base import BaseAgent
from src.domain.schemas.chat import Message
from src.utils.decorators import singleton
from src.utils.logger_conf import logger


SUMMARY_PROMPT_TEMPLATE = """You are a conversation summary expert. Your task is to summarize a conversation history into a single comprehensive paragraph that preserves all important context.

**WHAT TO INCLUDE:**
- Key facts, data points, and conclusions mentioned
- Important entities (companies, people, dates, numbers)
- Main topics and themes discussed
- Critical context needed to understand the current conversation flow
- Any decisions made or important insights discovered

**WHAT TO EXCLUDE:**
- Repetitive information
- Casual greetings and pleasantries
- Redundant explanations of the same concept

**OUTPUT REQUIREMENTS:**
- Single paragraph
- Concise but comprehensive
- Maintains logical flow
- Preserves all crucial information for context continuity
"""


@singleton
class SummaryAgent(BaseAgent):
    """Agent responsible for summarizing conversation history when it exceeds token limits."""

    def __init__(self):
        super().__init__()
        logger.info("Summary Agent initialized successfully.")

    def count_tokens(self, messages: List[Message]) -> int:
        """Count tokens in conversation history."""
        return self.llm.get_num_tokens(get_buffer_string(messages))

    async def ainvoke(self, messages: List[Message]) -> str:
        """Summarize conversation history to preserve key context while reducing tokens."""
        try:
            conversation_text = self._format_messages_for_summary(messages)
            system_prompt = SystemMessage(content=SUMMARY_PROMPT_TEMPLATE)
            user_prompt = HumanMessage(
                content=f"""Please analyze and summarize the following conversation history:{conversation_text}
                        Extract the key insights, main topics, important context, and recent context that should be preserved."""
            )
            messages = [system_prompt, user_prompt]
            response = await self.simple_llm_call(messages)
            return response.content

        except Exception as e:
            logger.error(f"Error generating conversation summary: {e}")
            return "Previous conversation context available but could not be fully summarized due to processing error."

    def _format_messages_for_summary(self, messages: List[Message]) -> str:
        """Format messages for summary analysis."""
        formatted = []
        for i, message in enumerate(messages):
            role = "User" if isinstance(message, HumanMessage) else "Assistant"
            content = getattr(message, "content", "")
            formatted.append(f"{role}: {content}")

        return "\n\n".join(formatted)

    def append_summary_to_user_message(
        self, user_message: HumanMessage, summary: str
    ) -> HumanMessage:
        """Append conversation summary to the user message content."""
        summary_prefix = f"[CONVERSATION CONTEXT: {summary}]\n\n"
        updated_content = summary_prefix + user_message.content

        return HumanMessage(content=updated_content)
