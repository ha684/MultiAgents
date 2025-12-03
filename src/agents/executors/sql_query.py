from typing import Any

from langchain_community.utilities.sql_database import SQLDatabase

from src.agents.graph.sql_graph import SqlGraph
from src.domain.entities.graph import SubgraphOutput
from src.domain.entities.state import SqlState


def _stringify_cell(v: Any, max_len: int = 160) -> str:
    """Safe, compact cell stringification for logs/prompts."""
    s = str(v)
    if len(s) > max_len:
        return s[: max_len - 1] + "…"
    return s


def _format_table_preview(rows: list[dict[str, Any]]) -> str:
    """Render a compact, readable table preview in markdown format."""
    if not rows:
        return "(No data returned)\n"

    first_cols = list(rows[0].keys())
    other_keys = []
    for r in rows:
        for k in r:
            if k not in first_cols and k not in other_keys:
                other_keys.append(k)
    cols = first_cols + other_keys

    header = "| " + " | ".join(cols) + " |\n"
    sep = "| " + " | ".join("---" for _ in cols) + " |\n"

    lines = [header, sep]
    for r in rows:
        line = "| " + " | ".join(_stringify_cell(r.get(c, "")) for c in cols) + " |\n"
        lines.append(line)
    return "".join(lines)


async def _run_sql_query(state: dict, sql_db: SQLDatabase) -> SubgraphOutput:
    """Execute SQL query subgraph and format comprehensive context without overloading the LLM."""
    sql_state = SqlState(direction=state["direction"])
    sql_graph = SqlGraph(sql_db)
    result = await sql_graph.ainvoke(state=sql_state)

    results_text = ""
    error_text = ""
    response_metadata: dict[str, Any] = result.state.get("response_metadata", {}) or {}

    no_content = not result.state.get("query_results", [])
    if result.status != "success" and no_content:
        error_text = f"SQL Subgraph Error: {result.message}\n\n"

    # Handle irrelevant queries
    if result.state.get("is_relevant") is False:
        irrelevance_reason = result.state.get("irrelevance_reason", "Unknown reason")
        suggested_rephrase = result.state.get("suggested_rephrase", "")

        error_text += "## Query Relevance Issue\n\n"
        error_text += f"**Reason:** {irrelevance_reason}\n\n"
        if suggested_rephrase:
            error_text += f"**Suggestion:** {suggested_rephrase}\n\n"
        error_text += "**Action Required:** Please rephrase your question to match the available database schema.\n"

        return SubgraphOutput(
            main_context=error_text,
            cited_documents=[],
            response_metadata=response_metadata,
            subgraph_error=error_text,
        )

    # Handle relevant queries
    if result.state.get("is_relevant"):
        query_results: list[dict[str, Any]] = (
            result.state.get("query_results", []) or []
        )

        if query_results:
            successful_queries = [qr for qr in query_results if qr.get("success")]
            failed_queries = [qr for qr in query_results if not qr.get("success")]

            # Start with clear status for the agent
            if successful_queries and not failed_queries:
                results_text = "✅ **Database query executed successfully. The results below are final and complete.**\n\n"
            else:
                results_text = "## Query Results\n\n"

            # Display successful queries
            if successful_queries:
                for idx, res in enumerate(successful_queries, 1):
                    if len(successful_queries) > 1:
                        results_text += (
                            f"**Query {idx}:** {res.get('purpose', 'N/A')}\n\n"
                        )

                    preview_rows = res.get("results_preview", [])
                    total_rows = int(res.get("row_count") or 0)
                    truncated = bool(
                        res.get("truncated") or (total_rows > len(preview_rows))
                    )

                    results_text += _format_table_preview(preview_rows)
                    results_text += "\n"

                    if truncated:
                        results_text += f"*Showing {len(preview_rows)} of {total_rows} rows. To view all rows, export or query the database directly.*\n\n"
                results_text += """When you receive SQL query results:
- If the status shows "successfully" and "final and complete", accept the results as-is
- A numeric result of 0 means zero records/items exist - this is a valid answer, not an error"""
            if failed_queries:
                results_text += f"\n### Failed Queries ({len(failed_queries)})\n\n"

                for idx, res in enumerate(failed_queries, 1):
                    results_text += f"**Query {idx}:** {res.get('purpose', 'N/A')}\n"
                    results_text += f"Error: {res.get('error', 'Unknown error')}\n\n"

                error_text += f"⚠️ Warning: {len(failed_queries)} out of {len(query_results)} queries failed execution.\n"

            # Visualization info
            if result.state.get("chart_spec"):
                results_text += "### Visualization\n"
                results_text += (
                    "A chart visualization has been generated for this data.\n\n"
                )
                response_metadata["sql_chart_spec"] = result.state.get("chart_spec")

            response_metadata.update(
                {
                    "total_queries": len(query_results),
                    "successful_queries": len(successful_queries),
                    "failed_queries": len(failed_queries),
                    "query_successful": len(failed_queries) == 0,
                    "max_rows_per_query": result.state.get("response_metadata", {}).get(
                        "max_rows_per_query"
                    ),
                }
            )
        else:
            results_text += "## No Queries Executed\n\n"
            results_text += "The system determined that no SQL queries were needed to answer your request.\n"

    return SubgraphOutput(
        main_context=results_text,
        cited_documents=[],
        response_metadata=response_metadata,
        subgraph_error=error_text,
    )


class SqlQueryExecutor:
    def __init__(self, sql_db: SQLDatabase):
        self.sql_db = sql_db

    async def __call__(self, state: dict) -> SubgraphOutput:
        return await _run_sql_query(state, self.sql_db)
