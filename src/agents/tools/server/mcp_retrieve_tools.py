# src/agents/tools/server/mcp_retrieve_tools.py
from typing import Any, Dict, List

from langchain_core.documents import Document
from langchain_core.tools import tool

from src.core.config.settings import settings
from src.rag.vectorstores import vector_retrieval
from src.services.web_search_service import web_search_service
from src.utils.logger_conf import logger


async def rag_search(query: str, context_metadata: Dict[str, Any]) -> List[Document]:
    """
    Args:
        query (str): The search query to find relevant content
        context_metadata (Dict[str, Any]): The metadata of the search
    """
    if not query:
        raise ValueError("user query is required")
    top_k = 50
    top_n = 5
    kb_id = context_metadata["kb_id"]
    filters = None
    try:
        results = await vector_retrieval.retrieve(
            kb_id=kb_id, query=query, top_k=top_k, top_n=top_n, filters=filters
        )
        return results

    except Exception as e:
        logger.error("Error in search from RAG")
        raise e


async def web_search(query: str) -> List[Document]:
    """
    Args:
        query (str): The search query to find relevant content
        context_metadata (Dict[str, Any]): The metadata of the search
    """
    retrieved_docs = await web_search_service.search(
        query=query,
        provider=settings.websearch_provider,
        max_results=5,
    )
    return retrieved_docs


@tool
async def think(thought: str) -> str:
    """Use this tool for strategic reasoning, planning, and verification throughout your task execution process.
    This tool serves as your thinking workspace to analyze problems, plan tool usage, evaluate results,
    and verify accuracy before providing responses.

    Use this tool to:
    - Break down complex user requests into manageable components
    - Plan which tools to use and in what sequence to accomplish the task
    - Evaluate tool results and determine if they meet the requirements
    - Identify gaps in information or functionality that need to be addressed
    - Verify that your planned response is accurate and well-supported
    - Check your reasoning and assumptions for potential errors
    - Record important information and sources that will support your final response
    - Assess task completion readiness before responding to the user

    Args:
        thought: Your reasoning process, such as:
                - Problem analysis and breakdown into actionable components
                - Tool selection and execution planning with expected outcomes
                - Evaluation of tool results against task requirements
                - Gap identification and strategy adjustment planning
                - Accuracy verification and claim validation
                - Source tracking and citation preparation
                - Self-reflection on reasoning quality and potential improvements
                - Final completeness assessment before task completion
    """
    return thought
