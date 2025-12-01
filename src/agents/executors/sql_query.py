from typing import Any

from src.agents.graph.sql_graph import SqlGraph
from src.database.sql_database import AsyncSQLDatabase
from src.domain.entities.graph import SubgraphOutput
from src.domain.entities.state import SqlState


def _stringify_cell(v: Any, max_len: int = 160) -> str:
    """Safe, compact cell stringification for logs/prompts."""
    s = str(v)
    if len(s) > max_len:
        return s[: max_len - 1] + "…"
    return s


def _format_table_preview(rows: list[dict[str, Any]]) -> str:
    """Render a compact, readable table preview without json.dumps."""
    if not rows:
        return "  (No data returned)\n"

    first_cols = list(rows[0].keys())
    other_keys = []
    for r in rows:
        for k in r:
            if k not in first_cols and k not in other_keys:
                other_keys.append(k)
    cols = first_cols + other_keys

    header = "  | " + " | ".join(cols) + " |\n"
    sep = "  | " + " | ".join("---" for _ in cols) + " |\n"

    lines = [header, sep]
    for r in rows:
        line = "  | " + " | ".join(_stringify_cell(r.get(c, "")) for c in cols) + " |\n"
        lines.append(line)
    return "".join(lines)


async def _run_sql_query(state: dict, sql_db: AsyncSQLDatabase) -> SubgraphOutput:
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

        error_text += "=== Query Relevance Issue ===\n\n"
        error_text += f"Reason: {irrelevance_reason}\n\n"
        if suggested_rephrase:
            error_text += f"Suggestion: {suggested_rephrase}\n\n"
        error_text += "Action Required: Please rephrase your question to match the available database schema.\n"

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
            results_text = "=== SQL Query Results ===\n\n"
            successful_queries = [qr for qr in query_results if qr.get("success")]
            failed_queries = [qr for qr in query_results if not qr.get("success")]

            # Display successful queries
            if successful_queries:
                results_text += f"Successful Queries: {len(successful_queries)}\n\n"

                for idx, res in enumerate(successful_queries, 1):
                    results_text += f"--- Query {idx} ---\n"
                    results_text += f"Purpose: {res.get('purpose', 'N/A')}\n\n"

                    if res.get("query"):
                        results_text += f"SQL Statement:\n{res['query']}\n\n"

                    preview_rows = res.get("results_preview", [])
                    total_rows = int(res.get("row_count") or 0)
                    truncated = bool(
                        res.get("truncated") or (total_rows > len(preview_rows))
                    )

                    # Display results
                    if total_rows == 0:
                        results_text += "Result: NO MATCHING RECORDS FOUND\n\n"
                        results_text += "Note: This query executed successfully but returned 0 rows.\n"
                        results_text += "This is NOT an error - it simply means there are no records matching your criteria.\n\n"
                    else:
                        results_text += f"Results (showing {len(preview_rows)} of {total_rows} rows):\n\n"
                        results_text += _format_table_preview(preview_rows)

                        if truncated:
                            results_text += "\n⚠️ TRUNCATION NOTICE:\n"
                            results_text += f"Only {len(preview_rows)} out of {total_rows} total rows are displayed above.\n"
                            results_text += (
                                "This is a hard-coded limit for text responses.\n"
                            )
                            results_text += f"To view all {total_rows} rows, the user must export or query the database directly.\n\n"
                        else:
                            results_text += (
                                f"\n✓ Complete results shown ({total_rows} rows)\n\n"
                            )

            # Display failed queries
            if failed_queries:
                results_text += f"\n=== Failed Queries: {len(failed_queries)} ===\n\n"

                for idx, res in enumerate(failed_queries, 1):
                    results_text += f"--- Failed Query {idx} ---\n"
                    results_text += f"Purpose: {res.get('purpose', 'N/A')}\n"
                    results_text += f"Error: {res.get('error', 'Unknown error')}\n"
                    if res.get("query"):
                        results_text += f"SQL Attempted:\n{res['query']}\n"
                    results_text += "\n"

                error_text += f"⚠️ Warning: {len(failed_queries)} out of {len(query_results)} queries failed execution.\n"

            # Visualization info
            if result.state.get("chart_spec"):
                results_text += "=== Visualization Available ===\n"
                results_text += (
                    "A chart visualization has been generated for this data.\n\n"
                )
                response_metadata["sql_chart_spec"] = result.state.get("chart_spec")

            # Summary
            results_text += "=== Execution Summary ===\n"
            results_text += f"Total Queries: {len(query_results)}\n"
            results_text += f"✓ Successful: {len(successful_queries)}\n"
            results_text += f"✗ Failed: {len(failed_queries)}\n"

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
            results_text += "=== No Queries Executed ===\n\n"
            results_text += "The system determined that no SQL queries were needed to answer your request.\n"

    return SubgraphOutput(
        main_context=results_text,
        cited_documents=[],
        response_metadata=response_metadata,
        subgraph_error=error_text,
    )


class SqlQueryExecutor:
    def __init__(self, sql_db: AsyncSQLDatabase):
        self.sql_db = sql_db

    async def __call__(self, state: dict) -> SubgraphOutput:
        return await _run_sql_query(state, self.sql_db)
