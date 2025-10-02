# src/agents/tools/server/mcp_retrieve_tools.py
from src.rag.vector import vector_retrieval
from src.utils.logger_conf import logger
from typing import Tuple, List, Dict, Any
from langchain_core.tools import tool


@tool
async def rag_search(
    query: str, top_k: int, top_n: int, context_metadata: Dict[str, Any]
) -> str:
    """
    Args:
        query (str): The search query to find relevant content
        top_k (int): Number of top embedding results to return
        top_n (int): Number of top reranking results to return
        context_metadata (Dict[str, Any]): The metadata of the search
    """
    if not query:
        raise ValueError("user query is required")

    kb_id = context_metadata["kb_id"]
    filters = None
    logger.info(
        f"Searching for {query} with top_k={top_k} and top_n={top_n} and kb_id={kb_id}"
    )
    try:
        results = await vector_retrieval.retrieve(
            kb_id=kb_id, query=query, top_k=top_k, top_n=top_n, filters=filters
        )

        document_ids = [doc.metadata.get("document_id", None) for doc in results]

        if not results:
            logger.error(
                "vector_retrieval.retrieve returned None - likely server error"
            )
            error_output = "**Server Error**\n\n"
            error_output += "**Error Details:** Vector retrieval server is not responding or encountered an internal error.\n\n"
            error_output += "The search service is currently unavailable. Please try again later or contact support.\n"
            return error_output

        xml_output = "<documents>\n"

        for i, doc in enumerate(results):
            xml_output += f'  <document index="{i + 1}">\n'

            metadata = getattr(doc, "metadata", {})
            folder_path = metadata.get("folder_path", None)
            original_filename = metadata.get("original_filename", None)

            source = original_filename or folder_path or f"document_{i + 1}"
            xml_output += f"    <source>{source}</source>\n"

            if folder_path and original_filename:
                xml_output += f"    <folder_path>{folder_path}</folder_path>\n"

            content = getattr(doc, "page_content", "No content available")
            xml_output += "    <document_content>\n"
            xml_output += f"{content}\n"
            xml_output += "    </document_content>\n"

            xml_output += "  </document>\n"

        xml_output += "</documents>"

        return xml_output, document_ids

    except Exception as e:
        logger.error(f"Error in search: {str(e)}")
        error_output = "**Server Error**\n\n"
        error_output += (
            f"**Error Details:** Vector retrieval server error - {str(e)}\n\n"
        )
        error_output += "The search service encountered an error. Please check server logs and try again.\n"
        return error_output, []


@tool
async def web_search(
    query: str, top_k: int, top_n: int, context_metadata: Dict[str, Any]
) -> Tuple[str, List[str]]:
    """
    Args:
        query (str): The search query to find relevant content
        top_k (int): Number of top embedding results to return
        top_n (int): Number of top reranking results to return
        context_metadata (Dict[str, Any]): The metadata of the search
    """
    return "Formatted contents here", ["List of urls here"]


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
    logger.info(f"Think tool: {thought}")
    return thought
