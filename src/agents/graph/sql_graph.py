# src/agents/graph/sql_graph.py
"""
SQL Graph - Text-to-SQL subgraph for database querying with natural language
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.graph.base import GraphAgentBase
from src.agents.prompts.agent_prompts import PromptTemplates
from src.agents.shared.sql_validator import SqlValidator
from src.agents.tools.server.mcp_retrieve_tools import think
from src.database.sql_database import AsyncSQLDatabase
from src.domain.entities.graph import RunConfig
from src.domain.entities.state import SqlState
from src.domain.schemas.graph import (
    ChartGenerationSchema,
    RelevanceValidationSchema,
    SqlAnalysisSchema,
    SqlGenerationSchema,
)
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

    def __init__(self, sql_database: AsyncSQLDatabase):
        super().__init__()
        self.validator = SqlValidator()
        self.sql_database = sql_database
        self.graph_name = "SqlGraph"
        self.compiled_graph = self._build_graph()
        logger.info("SqlGraph initialized successfully with LangChain SQLDatabase.")

    @property
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
        max_iterations = 3
        schema_info = await self.sql_database.get_table_info()
        available_tables = ", ".join(self.sql_database.get_usable_table_names())

        direction = state["direction"]

        messages: list[BaseMessage] = [
            SystemMessage(content=PromptTemplates.RELEVANCE_VALIDATION_SYSTEM_PROMPT),
            AIMessage(
                content=f"Available tables: {available_tables}\n\nDatabase schema:\n{schema_info}"
            ),
            HumanMessage(content=f"Query:\n{direction}"),
        ]

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
                "response_metadata": {
                    "route": "sql_query",
                    "query_successful": False,
                    "error": "relevance_check_failed",
                },
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
                "response_metadata": {
                    "route": "sql_query",
                    "query_successful": False,
                    "error": "query_not_relevant_to_database",
                    "suggested_rephrase": suggested_rephrase,
                },
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
                "[route_after_relevance_check] Query is not relevant. Ending graph."
            )
            return END

        logger.info(
            "[route_after_relevance_check] Query is relevant. Routing to analyze_query."
        )
        return "analyze_query"

    async def analyze_query_node(self, state: SqlState) -> dict[str, Any]:
        """
        Analyzes user query to determine:
        1. What data is needed
        2. Whether visualization is appropriate
        3. How many queries might be needed
        """
        max_iterations = 5

        schema_info = await self.sql_database.get_table_info()
        direction = state["direction"]

        messages: list[BaseMessage] = [
            SystemMessage(content=PromptTemplates.SQL_ANALYSIS_SYSTEM_PROMPT),
            AIMessage(content=f"Database schema:\n{schema_info}"),
            HumanMessage(content=f"Direction:\n{direction}"),
        ]

        try:
            response = await self.iterative_llm_call_structured(
                messages=messages,
                llm_with_tools=self.thinking_llm,
                available_tools={"think": think},
                max_iterations=max_iterations,
                parse_fn=parse_sql_analysis_response,
                retry_prompt="Please provide the analysis in correct JSON format.",
            )

            logger.debug(f"[analyze_query] LLM raw response:\n{response}")

            if not response:
                logger.error(
                    "[analyze_query] Failed to analyze query after multiple attempts."
                )
                return {
                    "query_results": [],
                    "analysis": None,
                    "response_metadata": {
                        "route": "sql_query",
                        "query_successful": False,
                        "error": "analysis_failed",
                    },
                }

            return {"analysis": response}
        except Exception as e:
            import traceback

            logger.error("!!! CRASH INSIDE analyze_query_node !!!")
            logger.error(f"Error type: {type(e)}")
            logger.error(f"Error message: {e}")
            traceback.print_exc()

            return {
                "query_results": [],
                "analysis": None,
                "response_metadata": {"route": "sql_query", "error": str(e)},
            }

    async def generate_sql_queries_node(self, state: SqlState) -> dict[str, Any]:
        """
        Generates SQL queries based on the analysis.
        Can generate multiple queries if needed for complex requests.
        """
        max_iterations = 5
        query_plan = state.get("analysis", {}).get("required_queries")

        if not query_plan:
            logger.error(
                "[generate_sql_queries] No query plan found in state. Cannot generate SQL."
            )
            return {
                "query_results": [],
                "generated_queries": None,
                "response_metadata": {
                    "route": "sql_query",
                    "query_successful": False,
                    "error": "no_query_plan",
                },
            }

        schema_info = await self.sql_database.get_table_info()

        direction = state["direction"]

        messages: list[BaseMessage] = [
            SystemMessage(content=PromptTemplates.SQL_GENERATION_SYSTEM_PROMPT),
            AIMessage(
                content=f"Database schema:\n{schema_info}\n\nQuery plan:\n{json.dumps(query_plan, indent=2)}"
            ),
            HumanMessage(content=f"Direction:\n{direction}"),
        ]

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
                "response_metadata": {
                    "route": "sql_query",
                    "query_successful": False,
                    "error": "sql_generation_failed",
                },
            }

        generated_queries = response["queries"]
        logger.info(
            f"[generate_sql_queries] Successfully generated {len(generated_queries)} SQL queries."
        )

        return {
            "generated_queries": generated_queries,
            "response_metadata": {
                "query_count": len(generated_queries),
            },
        }

    async def validate_queries_node(self, state: SqlState) -> dict[str, Any]:
        """
        Validates all generated SQL queries.
        Ensures they are SELECT-only and safe to execute.
        """
        generated_queries = state.get("generated_queries")

        if not generated_queries:
            logger.error(
                "[validate_queries] No SQL queries found in state to validate."
            )
            return {
                "query_results": None,
                "response_metadata": {
                    "route": "sql_query",
                    "query_successful": False,
                    "error": "no_queries_to_validate",
                },
            }

        logger.info(f"[validate_queries] Validating {len(generated_queries)} queries.")
        validation_results = []
        all_valid = True
        issues = []

        for idx, query_info in enumerate(generated_queries):
            query = query_info.get("query", "")
            purpose = query_info.get("purpose", f"Query {idx + 1}")
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
            error_msg = f"Validation failed: {'; '.join(issues)}"
            logger.error(f"[validate_queries] {error_msg}")

            return {
                "query_results": validation_results,
                "response_metadata": {
                    "route": "sql_query",
                    "query_successful": False,
                    "error": "validation_failed",
                    "validation_issues": issues,
                },
            }

        logger.info("[validate_queries] All SQL queries validated successfully.")

        return {"query_results": validation_results}

    def route_after_validation(self, state: SqlState) -> str:
        """Routes after SQL validation."""

        validation_results = state.get("query_results", [])
        if not validation_results:
            logger.error(
                "[route_after_validation] No validation results found. Ending graph."
            )
            return END

        logger.info(
            "[route_after_validation] All queries are valid. Routing to execute_queries."
        )
        return "execute_queries"

    async def execute_queries_node(self, state: SqlState) -> dict[str, Any]:
        """
        Executes all validated SQL queries sequentially.
        Uses DatabaseSession for proper transaction management.
        """
        MAX_ROWS_PER_QUERY = 5
        validation_results = state.get("query_results", [])

        if not validation_results:
            logger.error("[execute_queries] No validated queries to execute.")
            return {
                "query_results": [],
                "response_metadata": {
                    "route": "sql_query",
                    "query_successful": False,
                    "error": "no_queries_to_execute",
                },
            }

        logger.info(f"[execute_queries] Executing {len(validation_results)} queries.")
        all_results: list[dict[str, Any]] = []

        for _idx, validation_info in enumerate(validation_results):
            sanitized_query = validation_info["validation"]["sanitized_query"]
            is_valid = validation_info["validation"]["is_valid"]
            purpose = validation_info["purpose"]

            if not is_valid:
                logger.error(f"Query '{purpose}' is not valid. Skipping execution.")
                issues = validation_info["validation"].get("issues") or []
                issue_text = ", ".join(map(str, issues))
                all_results.append(
                    {
                        "purpose": purpose,
                        "query": sanitized_query,
                        "results_preview": None,
                        "success": False,
                        "error": issue_text or "invalid_query",
                    }
                )
                continue

            result = await self.sql_database.run_no_throw(
                sanitized_query, fetch="all", include_columns=True
            )

            if isinstance(result, str) and result.startswith("Error:"):
                logger.error(f"Error executing query '{purpose}': {result}")
                all_results.append(
                    {
                        "purpose": purpose,
                        "query": sanitized_query,
                        "results_preview": None,
                        "success": False,
                        "error": result,
                    }
                )
                continue
            rows: list[dict[str, Any]] = result or []
            total_rows = len(rows)
            truncated = total_rows > MAX_ROWS_PER_QUERY
            preview_rows = rows[:MAX_ROWS_PER_QUERY]

            all_results.append(
                {
                    "purpose": purpose,
                    "query": sanitized_query,
                    "results_preview": preview_rows,
                    "row_count": total_rows,
                    "truncated": truncated,
                    "success": True,
                }
            )

        failed_queries = [r for r in all_results if not r["success"]]
        if failed_queries:
            return {
                "query_results": all_results,
                "response_metadata": {
                    "route": "sql_query",
                    "query_successful": False,
                    "error": "execution_failed",
                    "failed_queries": len(failed_queries),
                    "total_queries": len(all_results),
                    "max_rows_per_query": MAX_ROWS_PER_QUERY,
                },
            }

        return {
            "query_results": all_results,
            "response_metadata": {
                **state.get("response_metadata", {}),
                "total_queries": len(all_results),
                "max_rows_per_query": MAX_ROWS_PER_QUERY,
            },
        }

    def route_after_execution(self, state: SqlState) -> str:
        """Routes after query execution."""
        analysis = state.get("analysis", {})
        if analysis.get("needs_chart") and analysis.get("chart_type"):
            logger.info(
                "[route_after_execution] Chart is needed. Routing to generate_chart."
            )
            return "generate_chart"

        return END

    async def generate_chart_node(self, state: SqlState) -> dict[str, Any]:
        """
        Generates Vega-Lite chart specification based on query results.
        Only called when analysis indicates visualization is appropriate.
        """
        max_iterations = 5

        if not state.get("query_results"):
            logger.warning(
                "[generate_chart] No query results found in state for chart generation. Skipping."
            )
            return {"chart_spec": None}

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
                        "columns": (
                            list(result["results"][0].keys())
                            if result["results"]
                            else []
                        ),
                        "statistical_summary": statistical_summary_str,
                    }
                )

        if not data_summary:
            logger.warning(
                "[generate_chart] No successful query results to use for chart generation. Skipping."
            )
            return {"chart_spec": None}

        chart_type = state.get("analysis", {}).get("chart_type", "auto")
        direction = state["direction"]

        messages: list[BaseMessage] = [
            SystemMessage(content=PromptTemplates.CHART_GENERATION_SYSTEM_PROMPT),
            AIMessage(
                content=f"Suggested chart type: {chart_type}\n\nQuery results summary:\n{json.dumps(data_summary, indent=2, default=str)}"
            ),
            HumanMessage(content=f"Direction:\n{direction}"),
        ]

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

        return {
            "chart_spec": response["vega_spec"],
            "response_metadata": updated_metadata,
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

        workflow.set_entry_point("validate_relevance")

        workflow.add_conditional_edges(
            "validate_relevance",
            self.route_after_relevance_check,
            {
                "analyze_query": "analyze_query",
                END: END,
            },
        )

        workflow.add_edge("analyze_query", "generate_sql_queries")
        workflow.add_edge("generate_sql_queries", "validate_queries")

        workflow.add_conditional_edges(
            "validate_queries",
            self.route_after_validation,
            {
                "execute_queries": "execute_queries",
                END: END,
            },
        )

        workflow.add_conditional_edges(
            "execute_queries",
            self.route_after_execution,
            {
                "generate_chart": "generate_chart",
                END: END,
            },
        )

        workflow.set_finish_point("generate_chart")

        return workflow.compile(name=self.graph_name)


def parse_sql_analysis_response(content: str) -> SqlAnalysisSchema | None:
    """Parse SQL analysis response"""
    try:
        parsed = parse_response(content)
        if not parsed:
            logger.warning(
                "[Parser] Failed to parse SQL analysis response (null result)."
            )
            return content
        response = SqlAnalysisSchema(**parsed)
        return response.model_dump()
    except Exception as e:
        logger.error(
            f"[Parser] Error parsing SQL analysis response: {e}", exc_info=True
        )
        return content


def parse_sql_generation_response(content: str) -> SqlGenerationSchema | None:
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


def parse_chart_generation_response(content: str) -> ChartGenerationSchema | None:
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
) -> RelevanceValidationSchema | None:
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
