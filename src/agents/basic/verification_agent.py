# src/agents/basic/verification_agent.py
from typing import List

from langchain_core.documents import Document
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from src.agents.basic.base import BaseAgent
from src.agents.tools.server.mcp_retrieve_tools import think
from src.core.config.llm_config import SupportedLLMProviders
from src.utils.decorators import singleton
from src.utils.logger_conf import logger

VERIFICATION_PROMPT_TEMPLATE = """
"""


@singleton
class VerificationAgent(BaseAgent):
    """Agent responsible for verifying information from relevant documents."""

    def __init__(self, provider: SupportedLLMProviders = "nxchat"):
        super().__init__(provider)
        logger.info("Verification Agent initialized successfully.")

    async def ainvoke(self, query: str, reference: List[Document]) -> str:
        """
        Verifies information from relevant documents.
        """
        if not reference:
            logger.warning("No relevant documents to verify")
            return ""

        fallback = "\n\n".join([doc.page_content for doc in reference])

        try:
            system_prompt = SystemMessage(content=VERIFICATION_PROMPT_TEMPLATE)
            user_content = HumanMessage(
                content=f"""Query: {query}\n\n---\n\nExtract and organize all relevant information from these documents. Remember: extract information, don't answer the query."""
            )
            messages: List[BaseMessage] = [system_prompt, user_content]

            response = await self.iterative_llm_call_text(
                messages=messages,
                llm_with_tools=self.thinking_llm,
                available_tools={"think": think},
                max_iterations=10,
                retry_prompt="Please provide your output again.",
                fallback_value=fallback,
            )

            compressed_content = response.content
            return compressed_content

        except Exception as e:
            logger.error(f"Error verifying information: {e}", exc_info=True)
            logger.warning("Using fallback: returning raw document content")
            return fallback
