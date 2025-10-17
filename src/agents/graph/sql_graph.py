# src/agents/graph/sql_graph.py
"""
SQL Graph - Text-to-SQL subgraph for database querying with natural language
"""

import json
from typing import Any, Dict, List, Optional

import pandas as pd
from langchain_community.utilities import SQLDatabase
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.basic.base import AgentBase
from src.agents.graph.prompts import PromptTemplates
from src.agents.graph.schemas import (
    SqlGenerationSchema,
    SqlAnalysisSchema,
    ChartGenerationSchema,
)
from src.agents.com.sql_validator import SqlValidator
from src.agents.graph.state import SqlState
from src.agents.tools.server.mcp_retrieve_tools import think
from src.config.settings import settings
from src.db.repository.database_session import DatabaseSession
from src.llm.factory import get_llm
from src.utils import parse_response
from src.utils.logger_conf import logger


class SqlGraph(AgentBase):
    """
    SQL Subgraph - Converts natural language queries to SQL and executes them safely.

    Features:
    - Uses LangChain SQLDatabase for optimized schema handling
    - Supports multi-query execution for complex requests
    - Auto-generates Vega-Lite charts when appropriate
    - Security: Only SELECT queries allowed
    """

    def __init__(self):
        self.llm = get_llm("nxchat")
        self.thinking_llm = self.llm.bind_tools([think])
        self.validator = SqlValidator()

        self.sql_database = SQLDatabase.from_uri(
            settings.database_url,
            sample_rows_in_table_info=3,
            include_tables=None,
        )

        self.graph = self._build_graph()
        logger.info("SqlGraph initialized successfully with LangChain SQLDatabase.")

    async def analyze_query_node(self, state: SqlState) -> Dict[str, Any]:
        """
        Analyzes user query to determine:
        1. What data is needed
        2. Whether visualization is appropriate
        3. How many queries might be needed
        """
        max_iterations = 5

        system_prompt = SystemMessage(
            content=PromptTemplates.SQL_ANALYSIS_SYSTEM_PROMPT
        )

        schema_info = self.sql_database.get_table_info()

        user_prompt = HumanMessage(
            content=PromptTemplates.SQL_ANALYSIS_HUMAN_PROMPT.format(
                user_query=state["contextualized_query"],
                database_schema=schema_info,
            )
        )

        messages: List[BaseMessage] = [system_prompt, user_prompt]

        response = await self.iterative_llm_call_structured(
            messages=messages,
            llm_with_tools=self.thinking_llm,
            available_tools={"think": think},
            max_iterations=max_iterations,
            parse_fn=parse_sql_analysis_response,
            retry_prompt="Please provide the analysis in correct JSON format.",
        )

        if not response:
            logger.error("Failed to analyze query")
            return {
                "sql_error": "Failed to analyze query requirements",
                "analysis": None,
            }

        logger.info(
            f"Query analysis: needs_chart={response.get('needs_chart')}, "
            f"query_count={len(response.get('required_queries', []))}"
        )

        return {
            "analysis": response,
            "needs_chart": response.get("needs_chart", False),
            "query_plan": response.get("required_queries", []),
        }

    async def generate_sql_queries_node(self, state: SqlState) -> Dict[str, Any]:
        """
        Generates SQL queries based on the analysis.
        Can generate multiple queries if needed for complex requests.
        """
        max_iterations = 5

        if not state.get("query_plan"):
            logger.error("No query plan available")
            return {
                "sql_error": "No query plan available",
                "generated_queries": None,
            }

        system_prompt = SystemMessage(
            content=PromptTemplates.SQL_GENERATION_SYSTEM_PROMPT
        )

        schema_info = self.sql_database.get_table_info()

        user_prompt = HumanMessage(
            content=PromptTemplates.SQL_GENERATION_HUMAN_PROMPT.format(
                user_query=state["contextualized_query"],
                database_schema=schema_info,
                query_plan=json.dumps(state["query_plan"], indent=2),
            )
        )

        messages: List[BaseMessage] = [system_prompt, user_prompt]

        response = await self.iterative_llm_call_structured(
            messages=messages,
            llm_with_tools=self.thinking_llm,
            available_tools={"think": think},
            max_iterations=max_iterations,
            parse_fn=parse_sql_generation_response,
            retry_prompt="Please provide SQL queries in correct JSON format.",
        )

        if not response or not response.get("queries"):
            logger.error("Failed to generate SQL queries")
            return {
                "generated_queries": None,
                "sql_error": "Failed to generate SQL queries",
            }

        generated_queries = response["queries"]
        logger.info(f"Generated {len(generated_queries)} SQL queries")

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
        if not state.get("generated_queries"):
            logger.error("No SQL queries to validate")
            return {
                "validation_results": None,
                "sql_error": "No SQL queries to validate",
            }

        validation_results = []
        all_valid = True
        issues = []

        for idx, query_info in enumerate(state["generated_queries"]):
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
                issues.extend(
                    [f"{purpose}: {issue}" for issue in validation.get("issues", [])]
                )
                logger.warning(
                    f"Query validation failed for '{purpose}': {validation.get('issues')}"
                )

        if not all_valid:
            error_msg = f"Validation failed: {'; '.join(issues)}"
            logger.error(error_msg)
            return {
                "validation_results": validation_results,
                "sql_error": error_msg,
            }

        logger.info("All SQL queries validated successfully")
        return {
            "validation_results": validation_results,
        }

    def route_after_validation(self, state: SqlState) -> str:
        """Routes after SQL validation."""
        if state.get("sql_error"):
            logger.warning("SQL validation failed - routing to error handler")
            return "handle_sql_error"

        validation_results = state.get("validation_results", [])
        if not validation_results:
            logger.error("No validation results - routing to error handler")
            return "handle_sql_error"

        all_valid = all(
            v["validation"]["is_valid"] and v["validation"]["is_select_only"]
            for v in validation_results
        )

        if not all_valid:
            logger.error("Some queries failed validation - routing to error handler")
            return "handle_sql_error"

        logger.info("All queries validated - routing to execution")
        return "execute_queries"

    async def execute_queries_node(self, state: SqlState) -> Dict[str, Any]:
        """
        Executes all validated SQL queries sequentially.
        Uses DatabaseSession for proper transaction management.
        """
        validation_results = state.get("validation_results", [])

        if not validation_results:
            logger.error("No validated queries to execute")
            return {"sql_error": "No validated queries available for execution"}

        all_results = []

        try:
            async with DatabaseSession() as session:
                for idx, validation_info in enumerate(validation_results):
                    sanitized_query = validation_info["validation"]["sanitized_query"]
                    purpose = validation_info["purpose"]

                    logger.info(
                        f"Executing query {idx + 1}/{len(validation_results)}: {purpose}"
                    )

                    try:
                        result = await session.execute(sanitized_query)
                        rows = result.fetchall()
                        columns = result.keys()

                        query_results = [dict(zip(columns, row)) for row in rows]

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

                    except Exception as query_error:
                        logger.error(
                            f"Error executing query '{purpose}': {query_error}"
                        )
                        all_results.append(
                            {
                                "purpose": purpose,
                                "query": sanitized_query,
                                "results": None,
                                "row_count": 0,
                                "success": False,
                                "error": str(query_error),
                            }
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

        except Exception as e:
            logger.error(f"Error in query execution: {e}")
            return {
                "query_results": None,
                "sql_error": f"Database error: {str(e)}",
            }

    def route_after_execution(self, state: SqlState) -> str:
        """Routes after query execution."""
        if state.get("sql_error"):
            return "handle_sql_error"

        if state.get("needs_chart") and state.get("analysis", {}).get("chart_type"):
            logger.info("Routing to chart generation")
            return "generate_chart"

        logger.info("Routing to result formatting")
        return "format_results"

    async def generate_chart_node(self, state: SqlState) -> Dict[str, Any]:
        """
        Generates Vega-Lite chart specification based on query results.
        Only called when analysis indicates visualization is appropriate.
        """
        max_iterations = 5

        if not state.get("query_results"):
            logger.warning("No query results for chart generation")
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
                    summary_df = df.describe()
                    if not summary_df.empty:
                        statistical_summary_str = summary_df.to_string()
                except Exception as e:
                    logger.error(f"Error generating statistical summary: {e}")

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

        user_prompt = HumanMessage(
            content=PromptTemplates.CHART_GENERATION_HUMAN_PROMPT.format(
                user_query=state["original_query"],
                chart_type=state["analysis"].get("chart_type", "auto"),
                data_summary=json.dumps(data_summary, indent=2, default=str),
            )
        )

        messages: List[BaseMessage] = [system_prompt, user_prompt]

        response = await self.iterative_llm_call_structured(
            messages=messages,
            llm_with_tools=self.thinking_llm,
            available_tools={"think": think},
            max_iterations=max_iterations,
            parse_fn=parse_chart_generation_response,
            retry_prompt="Please provide valid Vega-Lite JSON specification.",
        )

        if not response or not response.get("vega_spec"):
            logger.warning("Failed to generate chart specification")
            return {"chart_spec": None}

        logger.info(f"Generated {response.get('chart_type', 'unknown')} chart")

        return {
            "chart_spec": response["vega_spec"],
            "response_metadata": {
                **state.get("response_metadata", {}),
                "has_chart": True,
                "chart_type": response.get("chart_type"),
            },
        }

    async def format_results_node(self, state: SqlState) -> Dict[str, Any]:
        """
        Formats query results into a natural language summary.
        Combines results from multiple queries if needed.
        """
        if state.get("sql_error"):
            return {}

        if not state.get("query_results"):
            logger.warning("No query results to format")
            return {"result_summary": "No results returned from the queries."}

        system_prompt = SystemMessage(
            content=PromptTemplates.SQL_RESULT_EXPLANATION_PROMPT
        )

        results_text = f"Original Question: {state['original_query']}\n\n"
        results_text += "Query Results:\n\n"

        for result in state["query_results"]:
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
                "Note: A visualization chart has been generated for this data.\n"
            )

        user_prompt = HumanMessage(content=results_text)
        messages = [system_prompt, user_prompt]

        response = await self.simple_llm_call(messages=messages, llm=self.llm)

        summary = response.content if response else "Results retrieved successfully."

        logger.info("Generated result summary")

        return {
            "result_summary": summary,
            "response_metadata": {
                **state.get("response_metadata", {}),
                "route": "sql_query",
                "query_successful": True,
            },
        }

    async def handle_sql_error_node(self, state: SqlState) -> Dict[str, Any]:
        """
        Handles SQL errors and generates user-friendly error messages.
        """
        error_message = state.get("sql_error", "Unknown SQL error occurred")

        logger.info(f"Handling SQL error: {error_message}")

        user_message = f"""I encountered an issue while processing your database query:

Original Question: {state["original_query"]}

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
                user_message += "\nValidation Issues:\n"
                for v in failed_validations:
                    user_message += f"\n{v['purpose']}:\n"
                    for issue in v["validation"].get("issues", []):
                        user_message += f"  - {issue}\n"

        user_message += """
For security reasons, only SELECT queries are allowed to read data from the database.
Operations that modify data (INSERT, UPDATE, DELETE, etc.) are not permitted.

Please rephrase your question or contact an administrator if you need write access.
"""

        return {
            "result_summary": user_message.strip(),
            "response_metadata": {
                **state.get("response_metadata", {}),
                "route": "sql_query",
                "query_successful": False,
                "error": error_message,
            },
        }

    def _build_graph(self) -> CompiledStateGraph:
        """Build SQL query graph with chart generation support."""
        workflow = StateGraph(SqlState)

        # Add nodes
        workflow.add_node("analyze_query", self.analyze_query_node)
        workflow.add_node("generate_sql_queries", self.generate_sql_queries_node)
        workflow.add_node("validate_queries", self.validate_queries_node)
        workflow.add_node("execute_queries", self.execute_queries_node)
        workflow.add_node("generate_chart", self.generate_chart_node)
        workflow.add_node("format_results", self.format_results_node)
        workflow.add_node("handle_sql_error", self.handle_sql_error_node)

        # Set entry point
        workflow.set_entry_point("analyze_query")

        # Add edges
        workflow.add_edge("analyze_query", "generate_sql_queries")
        workflow.add_edge("generate_sql_queries", "validate_queries")

        # Conditional routing after validation
        workflow.add_conditional_edges(
            "validate_queries",
            self.route_after_validation,
            {
                "execute_queries": "execute_queries",
                "handle_sql_error": "handle_sql_error",
            },
        )

        # Conditional routing after execution
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

        # Set finish points
        workflow.add_edge("format_results", END)
        workflow.add_edge("handle_sql_error", END)

        return workflow.compile(name="SqlGraph")

    async def run(self, state: SqlState) -> SqlState:
        """
        Run SQL graph with state.

        Args:
            state: SqlState with user query and context

        Returns:
            Updated SqlState with:
            - query_results: List of query results with metadata
            - chart_spec: Vega-Lite specification (if applicable)
            - result_summary: Natural language summary
            - sql_error: Error message (if any)
        """
        try:
            config = {"recursion_limit": 50}
            result = await self.graph.ainvoke(state, config=config)
            return result

        except Exception as e:
            logger.error(f"Error running SQL graph: {e}")
            return {
                **state,
                "sql_error": f"Graph execution error: {str(e)}",
                "result_summary": "An error occurred while processing your database query.",
                "response_metadata": {
                    "route": "sql_query",
                    "query_successful": False,
                    "error": str(e),
                },
            }


# Parser functions
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
