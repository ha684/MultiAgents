# src/agents/basic/folder_categorization_agent.py

import json
from typing import Dict

from langchain_core.prompts import ChatPromptTemplate

from src.core.config.llm_config import SupportedLLMProviders
from src.domain.schemas.agent import RelevantFolder
from src.llm.factory import get_llm
from src.prompts.get_prompt_template import load_prompt_template
from src.utils.decorators import singleton
from src.utils.logger_conf import logger


@singleton
class FolderCategorizationAgent:
    """Agent responsible for generating the final response based on verified context, citations, and history."""

    def __init__(self, provider: SupportedLLMProviders = "nxchat"):
        self.llm = get_llm(provider)
        self.structured_llm = self.llm.with_structured_output(RelevantFolder)
        self.response_prompt = ChatPromptTemplate.from_template(
            load_prompt_template(
                task_name="folder_categorization",
                language_code="en",
            )
        )
        self.response_chain = self.response_prompt | self.structured_llm
        logger.info("Folder Categorization Agent initialized successfully.")

    async def get_relevant_folder(
        self, query: str, folder_structure: Dict
    ) -> RelevantFolder:
        input_data = {
            "query": query,
            "folder_structure": json.dumps(folder_structure, indent=2),
        }

        relevant_folder = await self.response_chain.ainvoke(input_data)
        return relevant_folder
