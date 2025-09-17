from typing import List
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from src.llm.factory import get_llm
from src.utils.logger_conf import logger
from src.utils.decorators import singleton
from pydantic import BaseModel
import tiktoken


class ConversationSummary(BaseModel):
    """Model for conversation summary."""

    summary: str


SUMMARY_PROMPT_TEMPLATE = """
You are a conversation summary expert. Your task is to summarize a conversation history into a single comprehensive paragraph that preserves all important context.

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

Return only a JSON object with one key "summary" containing the paragraph summary.

Example: {"summary": "The conversation focused on analyzing Company A's performance across multiple dimensions. Key findings include 15% revenue growth in Q2 2023, a security incident in March 2023 affecting customer data, and identified bottlenecks in payment processing systems. The user has been conducting comparative analysis and recently asked about companies without security incidents, building on the earlier security analysis discussion."}
"""


@singleton
class SummaryAgent:
    """Agent responsible for summarizing conversation history when it exceeds token limits."""

    def __init__(self):
        self.llm = get_llm("nxchat")
        self.structured_llm = self.llm.with_structured_output(ConversationSummary)
        self.tokenizer = tiktoken.encoding_for_model("gpt-4o")
        logger.info("Summary Agent initialized successfully.")

    def count_tokens(self, messages: List[BaseMessage]) -> int:
        """Count tokens in conversation history."""
        total_tokens = 0
        for message in messages:
            content = getattr(message, "content", "")
            if content:
                total_tokens += len(self.tokenizer.encode(str(content)))
        return total_tokens

    async def summarize_conversation(
        self, messages: List[BaseMessage]
    ) -> ConversationSummary:
        """Summarize conversation history to preserve key context while reducing tokens."""
        try:
            conversation_text = self._format_messages_for_summary(messages)
            system_prompt = SystemMessage(content=SUMMARY_PROMPT_TEMPLATE)
            user_prompt = HumanMessage(
                content=f"""Please analyze and summarize the following conversation history:

{conversation_text}

Extract the key insights, main topics, important context, and recent context that should be preserved."""
            )

            summary_prompt = ChatPromptTemplate.from_messages(
                [system_prompt, user_prompt]
            )
            summary_chain = summary_prompt | self.structured_llm
            response = await summary_chain.with_retry().ainvoke({})
            return response

        except Exception as e:
            logger.error(f"Error generating conversation summary: {e}")
            return ConversationSummary(
                summary="Previous conversation context available but could not be fully summarized due to processing error."
            )

    def _format_messages_for_summary(self, messages: List[BaseMessage]) -> str:
        """Format messages for summary analysis."""
        formatted = []
        for i, message in enumerate(messages):
            role = "User" if isinstance(message, HumanMessage) else "Assistant"
            content = getattr(message, "content", "")
            formatted.append(f"{role}: {content}")

        return "\n\n".join(formatted)

    def append_summary_to_user_message(
        self, user_message: HumanMessage, summary: ConversationSummary
    ) -> HumanMessage:
        """Append conversation summary to the user message content."""
        summary_prefix = f"[CONVERSATION CONTEXT: {summary.summary}]\n\n"
        updated_content = summary_prefix + user_message.content

        return HumanMessage(content=updated_content)
