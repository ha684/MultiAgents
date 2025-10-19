# src/agents/graph/sql_graph.py
"""
SQL Graph - Text-to-SQL subgraph for database querying with natural language
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import pandas as pd
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.graph.base import GraphAgentBase, RunConfig
from src.agents.graph.prompts import PromptTemplates
from src.agents.graph.schemas import (
    SqlGenerationSchema,
    SqlAnalysisSchema,
    ChartGenerationSchema,
    RelevanceValidationSchema,
)
from src.agents.com.sql_validator import SqlValidator
from src.db.sql_database import AsyncSQLDatabase
from src.agents.graph.state import SqlState
from src.agents.tools.server.mcp_retrieve_tools import think
from src.config.settings import settings
from src.llm.factory import get_llm
from src.utils import parse_response
from src.utils.logger_conf import logger


class SqlGraph(GraphAgentBase[SqlState]):
    """
    SQL Subgraph - Converts natural language queries to SQL and executes them safely.

    Features:
    - Uses LangChain SQLDatabase for optimized schema handling
    - Supports multi-query execution for complex requests
    - Auto-generates Vega-Lite charts when appropriate
    - Security: Only SELECT queries allowed
    """

    allow_tables: List[str] = [
        "conversations",
        "messages",
        "knowledge_bases",
        "documents",
        "document_qa",
    ]

    def __init__(self):
        self.llm = get_llm("nxchat")
        self.thinking_llm = self.llm.bind_tools([think])
        self.validator = SqlValidator()

        self.sql_database = AsyncSQLDatabase.from_uri(
            database_uri=settings.database_url,
            sample_rows_in_table_info=3,
            include_tables=self.allow_tables,
        )

        self.graph_name = "SqlGraph"
        self.compiled_graph = self._build_graph(self.graph_name)
        logger.info("SqlGraph initialized successfully with LangChain SQLDatabase.")

    def graph(self) -> CompiledStateGraph:
        return self.compiled_graph

    def default_run_config(self) -> RunConfig:
        return RunConfig(
            graph_name=self.graph_name, recursion_limit=10, timeout_seconds=180
        )

    async def validate_relevance_node(self, state: SqlState) -> SqlState:
        """
        Validates if user query is relevant to available database tables.
        Fast check before expensive analysis/generation steps.
        """
        logger.info("[validate_relevance] Checking query relevance to database.")
        max_iterations = 3

        system_prompt = SystemMessage(
            content=PromptTemplates.RELEVANCE_VALIDATION_SYSTEM_PROMPT
        )

        schema_info = await self.sql_database.get_table_info()
        available_tables = ", ".join(self.allow_tables)

        user_prompt = HumanMessage(
            content=PromptTemplates.RELEVANCE_VALIDATION_HUMAN_PROMPT.format(
                user_query=state["contextualized_query"],
                available_tables=available_tables,
                database_schema=schema_info,
            )
        )

        messages: List[BaseMessage] = [system_prompt, user_prompt]

        logger.info("[validate_relevance] Calling LLM for relevance check.")
        response = await self.iterative_llm_call_structured(
            messages=messages,
            llm_with_tools=self.thinking_llm,
            available_tools={"think": think},
            max_iterations=max_iterations,
            parse_fn=parse_relevance_validation_response,
            retry_prompt="Please provide the relevance check in correct JSON format.",
        )

        if not response:
            logger.error(
                "[validate_relevance] Failed to validate relevance after multiple attempts."
            )
            return {
                "is_relevant": False,
                "irrelevance_reason": "Unable to determine query relevance to database.",
            }

        is_relevant = response.get("is_relevant", False)
        logger.info(f"[validate_relevance] Query relevance: {is_relevant}")

        if not is_relevant:
            reason = response.get(
                "reason", "Query does not match available database tables."
            )
            suggested_rephrase = response.get("suggested_rephrase")
            logger.info(f"[validate_relevance] Irrelevant query. Reason: {reason}")
            return {
                "is_relevant": False,
                "irrelevance_reason": reason,
                "suggested_rephrase": suggested_rephrase,
            }

        logger.info("[validate_relevance] Query is relevant to database.")
        return {"is_relevant": True}

    def route_after_relevance_check(self, state: SqlState) -> str:
        """Routes after relevance validation."""
        logger.info(
            "[route_after_relevance_check] Deciding route after relevance check."
        )

        if not state.get("is_relevant", False):
            logger.warning(
                "[route_after_relevance_check] Query is not relevant. Routing to handle_irrelevant_query."
            )
            return "handle_irrelevant_query"

        logger.info(
            "[route_after_relevance_check] Query is relevant. Routing to analyze_query."
        )
        return "analyze_query"

    async def analyze_query_node(self, state: SqlState) -> Dict[str, Any]:
        """
        Analyzes user query to determine:
        1. What data is needed
        2. Whether visualization is appropriate
        3. How many queries might be needed
        """
        logger.info("[analyze_query] Starting query analysis node.")
        logger.debug(
            f"[analyze_query] Contextualized query: {state['contextualized_query']}"
        )
        max_iterations = 5

        system_prompt = SystemMessage(
            content=PromptTemplates.SQL_ANALYSIS_SYSTEM_PROMPT
        )

        schema_info = await self.sql_database.get_table_info()

        user_prompt = HumanMessage(
            content=PromptTemplates.SQL_ANALYSIS_HUMAN_PROMPT.format(
                user_query=state["contextualized_query"],
                database_schema=schema_info,
            )
        )

        messages: List[BaseMessage] = [system_prompt, user_prompt]

        logger.info("[analyze_query] Calling LLM for query analysis.")
        response = await self.iterative_llm_call_structured(
            messages=messages,
            llm_with_tools=self.thinking_llm,
            available_tools={"think": think},
            max_iterations=max_iterations,
            parse_fn=parse_sql_analysis_response,
            retry_prompt="Please provide the analysis in correct JSON format.",
        )

        if not response:
            logger.error(
                "[analyze_query] Failed to analyze query after multiple attempts."
            )
            return {
                "sql_error": "Failed to analyze query requirements",
                "analysis": None,
            }

        logger.info(
            f"[analyze_query] Query analysis complete: needs_chart={response.get('needs_chart')}, "
            f"query_count={len(response.get('required_queries', []))}"
        )
        logger.debug(f"[analyze_query] Returning analysis: {response}")

        return {"analysis": response}

    async def generate_sql_queries_node(self, state: SqlState) -> Dict[str, Any]:
        """
        Generates SQL queries based on the analysis.
        Can generate multiple queries if needed for complex requests.
        """
        logger.info("[generate_sql_queries] Starting SQL generation node.")
        max_iterations = 5
        query_plan = state.get("analysis", {}).get("required_queries")

        if not query_plan:
            logger.error(
                "[generate_sql_queries] No query plan found in state. Cannot generate SQL."
            )
            return {
                "sql_error": "No query plan available to generate SQL",
                "generated_queries": None,
            }

        logger.debug(f"[generate_sql_queries] Using query plan: {query_plan}")

        system_prompt = SystemMessage(
            content=PromptTemplates.SQL_GENERATION_SYSTEM_PROMPT
        )

        schema_info = await self.sql_database.get_table_info()

        user_prompt = HumanMessage(
            content=PromptTemplates.SQL_GENERATION_HUMAN_PROMPT.format(
                user_query=state["contextualized_query"],
                database_schema=schema_info,
                query_plan=json.dumps(query_plan, indent=2),
            )
        )

        messages: List[BaseMessage] = [system_prompt, user_prompt]

        logger.info("[generate_sql_queries] Calling LLM to generate SQL.")
        response = await self.iterative_llm_call_structured(
            messages=messages,
            llm_with_tools=self.thinking_llm,
            available_tools={"think": think},
            max_iterations=max_iterations,
            parse_fn=parse_sql_generation_response,
            retry_prompt="Please provide SQL queries in correct JSON format.",
        )

        if not response or not response.get("queries"):
            logger.error(
                "[generate_sql_queries] Failed to generate SQL queries from LLM response."
            )
            return {
                "generated_queries": None,
                "sql_error": "Failed to generate SQL queries",
            }

        generated_queries = response["queries"]
        logger.info(
            f"[generate_sql_queries] Successfully generated {len(generated_queries)} SQL queries."
        )
        logger.debug(
            f"[generate_sql_queries] Returning generated queries: {generated_queries}"
        )

        return {
            "generated_queries": generated_queries,
            "response_metadata": {
                "query_count": len(generated_queries),
            },
        }

    async def validate_queries_node(self, state: SqlState) -> Dict[str, Any]:
        """
        Validates all generated SQL queries.
        Ensures they are SELECT-only and safe to execute.
        """
        logger.info("[validate_queries] Starting query validation node.")
        generated_queries = state.get("generated_queries")

        if not generated_queries:
            logger.error(
                "[validate_queries] No SQL queries found in state to validate."
            )
            return {
                "validation_results": None,
                "sql_error": "No SQL queries to validate",
            }

        logger.info(f"[validate_queries] Validating {len(generated_queries)} queries.")
        validation_results = []
        all_valid = True
        issues = []

        for idx, query_info in enumerate(generated_queries):
            query = query_info.get("query", "")
            purpose = query_info.get("purpose", f"Query {idx + 1}")
            logger.debug(
                f"[validate_queries] Validating query for purpose: '{purpose}'"
            )

            validation = self.validator.validate_query(query)

            validation_results.append(
                {
                    "purpose": purpose,
                    "original_query": query,
                    "validation": validation,
                }
            )

            if not validation["is_valid"] or not validation["is_select_only"]:
                all_valid = False
                validation_issues = validation.get("issues", [])
                issues.extend([f"{purpose}: {issue}" for issue in validation_issues])
                logger.warning(
                    f"[validate_queries] Validation FAILED for '{purpose}': {validation_issues}"
                )
            else:
                logger.info(f"[validate_queries] Validation PASSED for '{purpose}'.")

        if not all_valid:
            error_msg = (
                f"Validation failed for one or more queries: {'; '.join(issues)}"
            )
            logger.error(f"[validate_queries] {error_msg}")
            return {
                "validation_results": validation_results,
                "sql_error": error_msg,
            }

        logger.info("[validate_queries] All SQL queries validated successfully.")
        logger.debug(
            f"[validate_queries] Returning validation results: {validation_results}"
        )
        return {
            "validation_results": validation_results,
        }

    def route_after_validation(self, state: SqlState) -> str:
        """Routes after SQL validation."""
        logger.info("[route_after_validation] Deciding route after validation.")
        if state.get("sql_error"):
            logger.warning(
                "[route_after_validation] SQL error detected. Routing to handle_sql_error."
            )
            return "handle_sql_error"

        validation_results = state.get("validation_results", [])
        if not validation_results:
            logger.error(
                "[route_after_validation] No validation results found. Routing to handle_sql_error."
            )
            return "handle_sql_error"

        all_valid = all(
            v["validation"]["is_valid"] and v["validation"]["is_select_only"]
            for v in validation_results
        )

        if not all_valid:
            logger.error(
                "[route_after_validation] Some queries failed validation. Routing to handle_sql_error."
            )
            return "handle_sql_error"

        logger.info(
            "[route_after_validation] All queries are valid. Routing to execute_queries."
        )
        return "execute_queries"

    async def execute_queries_node(self, state: SqlState) -> Dict[str, Any]:
        """
        Executes all validated SQL queries sequentially.
        Uses DatabaseSession for proper transaction management.
        """
        logger.info("[execute_queries] Starting query execution node.")
        validation_results = state.get("validation_results", [])

        if not validation_results:
            logger.error("[execute_queries] No validated queries to execute.")
            return {"sql_error": "No validated queries available for execution"}

        logger.info(f"[execute_queries] Executing {len(validation_results)} queries.")
        all_results = []

        for idx, validation_info in enumerate(validation_results):
            sanitized_query = validation_info["validation"]["sanitized_query"]
            purpose = validation_info["purpose"]

            logger.info(
                f"Executing query {idx + 1}/{len(validation_results)}: {purpose}"
            )

            result = await self.sql_database.run_no_throw(
                sanitized_query, fetch="all", include_columns=True
            )

            if isinstance(result, str) and result.startswith("Error:"):
                logger.error(f"Error executing query '{purpose}': {result}")
                all_results.append(
                    {
                        "purpose": purpose,
                        "query": sanitized_query,
                        "results": None,
                        "row_count": 0,
                        "success": False,
                        "error": result,
                    }
                )
            else:
                query_results = result if isinstance(result, list) else []
                all_results.append(
                    {
                        "purpose": purpose,
                        "query": sanitized_query,
                        "results": query_results,
                        "row_count": len(query_results),
                        "success": True,
                    }
                )
                logger.info(
                    f"Query '{purpose}' executed successfully, returned {len(query_results)} rows"
                )

        failed_queries = [r for r in all_results if not r["success"]]
        if failed_queries:
            error_msgs = [f"{r['purpose']}: {r['error']}" for r in failed_queries]
            return {
                "query_results": all_results,
                "sql_error": f"Some queries failed: {'; '.join(error_msgs)}",
            }

        total_rows = sum(r["row_count"] for r in all_results)
        logger.info(
            f"All queries executed successfully, total {total_rows} rows returned"
        )

        return {
            "query_results": all_results,
            "response_metadata": {
                **state.get("response_metadata", {}),
                "total_queries": len(all_results),
                "total_rows": total_rows,
            },
        }

    def route_after_execution(self, state: SqlState) -> str:
        """Routes after query execution."""
        logger.info("[route_after_execution] Deciding route after execution.")
        if state.get("sql_error"):
            logger.warning(
                "[route_after_execution] SQL error detected during execution. Routing to handle_sql_error."
            )
            return "handle_sql_error"

        analysis = state.get("analysis", {})
        if analysis.get("needs_chart") and analysis.get("chart_type"):
            logger.info(
                "[route_after_execution] Chart is needed. Routing to generate_chart."
            )
            return "generate_chart"

        logger.info(
            "[route_after_execution] No chart needed. Routing to format_results."
        )
        return "format_results"

    async def generate_chart_node(self, state: SqlState) -> Dict[str, Any]:
        """
        Generates Vega-Lite chart specification based on query results.
        Only called when analysis indicates visualization is appropriate.
        """
        logger.info("[generate_chart] Starting chart generation node.")
        max_iterations = 5

        if not state.get("query_results"):
            logger.warning(
                "[generate_chart] No query results found in state for chart generation. Skipping."
            )
            return {"chart_spec": None}

        system_prompt = SystemMessage(
            content=PromptTemplates.CHART_GENERATION_SYSTEM_PROMPT
        )

        data_summary = []
        for result in state["query_results"]:
            if result.get("success") and result.get("results"):
                statistical_summary_str = None
                try:
                    df = pd.DataFrame(result["results"])
                    summary_df = df.describe(include="all")
                    if not summary_df.empty:
                        statistical_summary_str = summary_df.to_string()
                except Exception as e:
                    logger.error(
                        f"[generate_chart] Error generating statistical summary: {e}"
                    )

                data_summary.append(
                    {
                        "purpose": result["purpose"],
                        "sample_data": result["results"][:3],
                        "row_count": result["row_count"],
                        "columns": list(result["results"][0].keys())
                        if result["results"]
                        else [],
                        "statistical_summary": statistical_summary_str,
                    }
                )

        if not data_summary:
            logger.warning(
                "[generate_chart] No successful query results to use for chart generation. Skipping."
            )
            return {"chart_spec": None}

        logger.debug(f"[generate_chart] Prepared data summary for LLM: {data_summary}")
        user_prompt = HumanMessage(
            content=PromptTemplates.CHART_GENERATION_HUMAN_PROMPT.format(
                user_query=state["contextualized_query"],
                chart_type=state.get("analysis", {}).get("chart_type", "auto"),
                data_summary=json.dumps(data_summary, indent=2, default=str),
            )
        )

        messages: List[BaseMessage] = [system_prompt, user_prompt]

        logger.info("[generate_chart] Calling LLM to generate Vega-Lite spec.")
        response = await self.iterative_llm_call_structured(
            messages=messages,
            llm_with_tools=self.thinking_llm,
            available_tools={"think": think},
            max_iterations=max_iterations,
            parse_fn=parse_chart_generation_response,
            retry_prompt="Please provide valid Vega-Lite JSON specification.",
        )

        if not response or not response.get("vega_spec"):
            logger.warning(
                "[generate_chart] Failed to generate chart specification from LLM response."
            )
            return {"chart_spec": None}

        chart_type = response.get("chart_type", "unknown")
        logger.info(
            f"[generate_chart] Successfully generated {chart_type} chart specification."
        )

        updated_metadata = {
            **state.get("response_metadata", {}),
            "has_chart": True,
            "chart_type": chart_type,
        }
        logger.debug(
            f"[generate_chart] Returning chart spec and updated metadata: {updated_metadata}"
        )

        return {
            "chart_spec": response["vega_spec"],
            "response_metadata": updated_metadata,
        }

    async def format_results_node(self, state: SqlState) -> Dict[str, Any]:
        """
        Formats query results into a natural language summary.
        Combines results from multiple queries if needed.
        """
        logger.info("[format_results] Starting result formatting node.")
        if state.get("sql_error"):
            logger.warning(
                "[format_results] Skipping formatting due to prior SQL error."
            )
            return {}

        if not state.get("query_results"):
            logger.warning("[format_results] No query results to format.")
            return {"result_summary": "No data was returned from the database."}

        system_prompt = SystemMessage(
            content=PromptTemplates.SQL_RESULT_EXPLANATION_PROMPT
        )

        results_text = f"Original Question: {state['contextualized_query']}\n\n"
        results_text += "Query Results:\n\n"

        for result in state["query_results"]:
            if result.get("success"):
                results_text += f"Purpose: {result['purpose']}\n"
                results_text += f"Rows returned: {result['row_count']}\n"
                if result.get("results"):
                    results_text += "Sample data (first 10 rows):\n"
                    results_text += json.dumps(
                        result["results"][:10], indent=2, default=str
                    )
                results_text += "\n\n"

        if state.get("chart_spec"):
            results_text += (
                "Note: A visualization chart has also been generated for this data.\n"
            )

        logger.debug(
            f"[format_results] Text prepared for summarization LLM call: {results_text}"
        )
        user_prompt = HumanMessage(content=results_text)
        messages = [system_prompt, user_prompt]

        logger.info("[format_results] Calling LLM to summarize results.")
        response = await self.simple_llm_call(messages=messages, llm=self.llm)

        summary = (
            response.content
            if response
            else "The query was executed successfully, but a summary could not be generated."
        )

        logger.info("[format_results] Successfully generated result summary.")

        updated_metadata = {
            **state.get("response_metadata", {}),
            "route": "sql_query",
            "query_successful": True,
        }
        logger.debug(
            f"[format_results] Returning summary and final metadata: {updated_metadata}"
        )

        return {
            "result_summary": summary,
            "response_metadata": updated_metadata,
        }

    async def handle_sql_error_node(self, state: SqlState) -> Dict[str, Any]:
        """
        Handles SQL errors and generates user-friendly error messages.
        """
        logger.info("[handle_sql_error] Starting error handling node.")
        error_message = state.get(
            "sql_error", "An unknown error occurred during the SQL process."
        )

        logger.error(f"[handle_sql_error] Handling reported error: {error_message}")

        user_message = f"""I encountered an issue while processing your database query.

Original Question: {state["contextualized_query"]}

Issue: {error_message}
"""

        if state.get("validation_results"):
            failed_validations = [
                v
                for v in state["validation_results"]
                if not v["validation"]["is_valid"]
                or not v["validation"]["is_select_only"]
            ]

            if failed_validations:
                user_message += "\n\nDetails on Validation Issues:\n"
                for v in failed_validations:
                    user_message += f"\nFor query purpose '{v['purpose']}':\n"
                    for issue in v["validation"].get("issues", []):
                        user_message += f"  - {issue}\n"

        user_message += """
\nFor security and data integrity, I can only perform read-only (SELECT) queries.
Any requests to modify data (like INSERT, UPDATE, DELETE) are not permitted.

Please try rephrasing your question to only request information, or contact a system administrator if you believe this is an error.
"""

        final_summary = user_message.strip()
        logger.info("[handle_sql_error] Generated user-facing error message.")

        updated_metadata = {
            **state.get("response_metadata", {}),
            "route": "sql_query",
            "query_successful": False,
            "error": error_message,
        }
        logger.debug(
            f"[handle_sql_error] Returning error summary and final metadata: {updated_metadata}"
        )

        return {
            "result_summary": final_summary,
            "response_metadata": updated_metadata,
        }

    async def handle_irrelevant_query_node(self, state: SqlState) -> Dict[str, Any]:
        """
        Handles queries that are not relevant to the database.
        Provides helpful feedback to user.
        """
        logger.info("[handle_irrelevant_query] Handling irrelevant query.")

        reason = state.get(
            "irrelevance_reason",
            "Your query doesn't match the available database tables.",
        )
        suggested_rephrase = state.get("suggested_rephrase")

        user_message = f"""I understand you're asking: "{state["contextualized_query"]}"

    However, this question doesn't appear to be related to the data available in the database.

    {reason}

    **Available Data Sources:**
    I can help you query information from these tables:
    """

        for table in self.allow_tables:
            user_message += f"\n- **{table}**: "
            if table == "conversations":
                user_message += "Chat conversation records"
            elif table == "messages":
                user_message += "Individual messages within conversations"
            elif table == "knowledge_bases":
                user_message += "Knowledge base configurations"
            elif table == "documents":
                user_message += "Uploaded documents and files"
            elif table == "document_qa":
                user_message += "Question-answer pairs from documents"

        if suggested_rephrase:
            user_message += f"\n\n**Suggestion:** {suggested_rephrase}"
        else:
            user_message += "\n\n**Tip:** Try asking questions about conversations, messages, documents, or knowledge bases stored in the system."

        logger.info(
            "[handle_irrelevant_query] Generated user-friendly irrelevance message."
        )

        return {
            "result_summary": user_message,
            "response_metadata": {
                "route": "sql_query",
                "query_successful": False,
                "error": "query_not_relevant_to_database",
                "is_relevant": False,
            },
        }

    def _build_graph(self) -> CompiledStateGraph:
        """Build SQL query graph with relevance validation and chart generation support."""
        workflow = StateGraph(SqlState)

        workflow.add_node("validate_relevance", self.validate_relevance_node)
        workflow.add_node("analyze_query", self.analyze_query_node)
        workflow.add_node("generate_sql_queries", self.generate_sql_queries_node)
        workflow.add_node("validate_queries", self.validate_queries_node)
        workflow.add_node("execute_queries", self.execute_queries_node)
        workflow.add_node("generate_chart", self.generate_chart_node)
        workflow.add_node("format_results", self.format_results_node)
        workflow.add_node("handle_sql_error", self.handle_sql_error_node)
        workflow.add_node("handle_irrelevant_query", self.handle_irrelevant_query_node)

        workflow.set_entry_point("validate_relevance")

        workflow.add_conditional_edges(
            "validate_relevance",
            self.route_after_relevance_check,
            {
                "analyze_query": "analyze_query",
                "handle_irrelevant_query": "handle_irrelevant_query",
            },
        )

        workflow.add_edge("analyze_query", "generate_sql_queries")
        workflow.add_edge("generate_sql_queries", "validate_queries")

        workflow.add_conditional_edges(
            "validate_queries",
            self.route_after_validation,
            {
                "execute_queries": "execute_queries",
                "handle_sql_error": "handle_sql_error",
            },
        )

        workflow.add_conditional_edges(
            "execute_queries",
            self.route_after_execution,
            {
                "generate_chart": "generate_chart",
                "format_results": "format_results",
                "handle_sql_error": "handle_sql_error",
            },
        )

        workflow.add_edge("generate_chart", "format_results")

        workflow.add_edge("format_results", END)
        workflow.add_edge("handle_sql_error", END)
        workflow.add_edge("handle_irrelevant_query", END)

        return workflow.compile(name=self.graph_name)


def parse_sql_analysis_response(content: str) -> Optional[SqlAnalysisSchema]:
    """Parse SQL analysis response"""
    try:
        parsed = parse_response(content)
        if not parsed:
            logger.warning(
                "[Parser] Failed to parse SQL analysis response (null result)."
            )
            return None
        response = SqlAnalysisSchema(**parsed)
        return response.model_dump()
    except Exception as e:
        logger.error(
            f"[Parser] Error parsing SQL analysis response: {e}", exc_info=True
        )
        return None


def parse_sql_generation_response(content: str) -> Optional[SqlGenerationSchema]:
    """Parse SQL generation response"""
    try:
        parsed = parse_response(content)
        if not parsed:
            logger.warning(
                "[Parser] Failed to parse SQL generation response (null result)."
            )
            return None
        response = SqlGenerationSchema(**parsed)
        return response.model_dump()
    except Exception as e:
        logger.error(
            f"[Parser] Error parsing SQL generation response: {e}", exc_info=True
        )
        return None


def parse_chart_generation_response(content: str) -> Optional[ChartGenerationSchema]:
    """Parse chart generation response"""
    try:
        parsed = parse_response(content)
        if not parsed:
            logger.warning(
                "[Parser] Failed to parse chart generation response (null result)."
            )
            return None
        response = ChartGenerationSchema(**parsed)
        return response.model_dump()
    except Exception as e:
        logger.error(
            f"[Parser] Error parsing chart generation response: {e}", exc_info=True
        )
        return None


def parse_relevance_validation_response(
    content: str,
) -> Optional[RelevanceValidationSchema]:
    """Parse relevance validation response"""
    try:
        parsed = parse_response(content)
        if not parsed:
            logger.warning(
                "[Parser] Failed to parse relevance validation response (null result)."
            )
            return None
        response = RelevanceValidationSchema(**parsed)
        return response.model_dump()
    except Exception as e:
        logger.error(
            f"[Parser] Error parsing relevance validation response: {e}", exc_info=True
        )
        return None
