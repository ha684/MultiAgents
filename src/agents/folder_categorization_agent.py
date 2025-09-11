# src/agents/response_agent.py

import json
from typing import Dict
from langchain_core.prompts import ChatPromptTemplate
from src.config.llm_config import SupportedLLMProviders
from src.llm.factory import get_llm
from src.models.agent import RelevantFolder
from src.prompts.get_prompt_template import load_prompt_template
from src.utils.logger_conf import logger
from src.utils.decorators import singleton


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


# Example Usage (Optional - for testing)
if __name__ == "__main__":
    # Requires OPENAI_API_KEY to be set

    response_agent = FolderCategorizationAgent()

    sample_folder_structure = {
        "API Reference": "Comprehensive technical documentation of all REST and GraphQL APIs.",
        "Authentication": "Guides and configs for user login, token handling, and OAuth flows.",
        "Deployment & CI": "Instructions and YAML pipelines for CI/CD, staging, and production environments.",
        "Testing Framework": "Details about automated tests, test environments, and QA processes.",
        "Release Process": "Checklists and steps for final release, sign-off, and change approvals.",
        "Monitoring & Alerts": "Describes logging setup, dashboards, error reporting, and system health alerts.",
        "Developer Onboarding": "Resources for new developers: repo setup, code style, environment config.",
        "Product Requirements": "User stories, feature specs, and acceptance criteria.",
        "Data Models": "Schema definitions, ERDs, and relationships between entities.",
        "Meeting Notes": "Weekly sync summaries, decisions made, and team blockers.",
        "User Documentation": "End-user help articles, UI walkthroughs, and troubleshooting tips.",
    }

    test_query = "Where can I find the API documentation for the new service?"
    print("\n--- Test Case 1: API Docs ---")
    response_1 = response_agent.get_relevant_folder(test_query, sample_folder_structure)
    print(f"Generated Response:\n{response_1}")

    test_query = "How is the application deployed to staging?"

    print("\n--- Test Case 2: Deployment ---")
    response_2 = response_agent.get_relevant_folder(test_query, sample_folder_structure)
    print(f"Generated Response:\n{response_2}")

    test_query = "What is the vacation policy for employees?"

    print("\n--- Test Case 14: No Match — HR Policy ---")
    response_14 = response_agent.get_relevant_folder(
        test_query, sample_folder_structure
    )
    print(f"Generated Response:\n{response_14}")
