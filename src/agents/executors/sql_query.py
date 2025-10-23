# src/agents/executors/sql_query.py
import json

from src.agents.graph.state import OrchestratorState, SqlState
from src.agents.com.types import SubgraphOutput
from src.agents.graph import sql_graph


async def _run_sql_query(state: OrchestratorState) -> SubgraphOutput:
    """Execute SQL query subgraph and format comprehensive context"""
    sql_state = SqlState(contextualized_query=state["contextualized_query"])
    result = await sql_graph.ainvoke(state=sql_state)

    results_text = ""
    error_text = ""
    response_metadata = result.state.get("response_metadata", {})

    if result.status != "success":
        error_text = f"SQL Subgraph Error: {result.message}\n\n"

    if result.state.get("is_relevant") is False:
        irrelevance_reason = result.state.get("irrelevance_reason", "Unknown reason")
        suggested_rephrase = result.state.get("suggested_rephrase", "")

        error_text += "Query Relevance Issue:\n"
        error_text += f"- Reason: {irrelevance_reason}\n"
        if suggested_rephrase:
            error_text += f"- Suggested rephrase: {suggested_rephrase}\n"

        return SubgraphOutput(
            main_context=error_text,
            cited_documents=[],
            response_metadata=response_metadata,
            subgraph_error=error_text,
        )

    if result.state.get("is_relevant"):
        query_results = result.state.get("query_results", [])

        if query_results:
            results_text = "=== SQL Query Execution Results ===\n\n"
            results_text += f"Original Question: {state['contextualized_query']}\n\n"

            successful_queries = [qr for qr in query_results if qr.get("success")]
            failed_queries = [qr for qr in query_results if not qr.get("success")]

            if successful_queries:
                results_text += (
                    f"--- Successful Queries ({len(successful_queries)}) ---\n\n"
                )

                for idx, res in enumerate(successful_queries, 1):
                    results_text += f"Query {idx}:\n"
                    results_text += f"  Purpose: {res.get('purpose', 'N/A')}\n"
                    results_text += f"  Rows returned: {res.get('row_count', 0)}\n"

                    if res.get("query"):
                        results_text += f"  SQL: {res['query']}\n"

                    if res.get("results") and res.get("row_count", 0) > 0:
                        sample_size = min(3, len(res["results"]))
                        results_text += f"  Sample data (first {sample_size} rows):\n"
                        results_text += "  " + json.dumps(
                            res["results"][:sample_size], indent=2, default=str
                        ).replace("\n", "\n  ")
                        results_text += "\n"
                    else:
                        results_text += "  Note: Query executed successfully but returned no rows.\n"

                    results_text += "\n"

                total_rows = sum(qr.get("row_count", 0) for qr in successful_queries)
                results_text += (
                    f"Total rows across all successful queries: {total_rows}\n\n"
                )

            if failed_queries:
                results_text += f"--- Failed Queries ({len(failed_queries)}) ---\n\n"

                for idx, res in enumerate(failed_queries, 1):
                    results_text += f"Failed Query {idx}:\n"
                    results_text += f"  Purpose: {res.get('purpose', 'N/A')}\n"
                    results_text += f"  Error: {res.get('error', 'Unknown error')}\n"

                    if res.get("query"):
                        results_text += f"  SQL: {res['query']}\n"

                    results_text += "\n"

                error_text += f"Warning: {len(failed_queries)} out of {len(query_results)} queries failed.\n"

            if result.state.get("chart_spec"):
                results_text += "--- Visualization ---\n"
                results_text += (
                    "A visualization chart has been generated for this data.\n\n"
                )
                response_metadata["sql_chart_spec"] = result.state.get("chart_spec")

            results_text += "=== Execution Summary ===\n"
            results_text += f"Total queries executed: {len(query_results)}\n"
            results_text += f"Successful: {len(successful_queries)}\n"
            results_text += f"Failed: {len(failed_queries)}\n"

            response_metadata.update(
                {
                    "total_queries": len(query_results),
                    "successful_queries": len(successful_queries),
                    "failed_queries": len(failed_queries),
                    "query_successful": len(failed_queries) == 0,
                }
            )

        else:
            results_text = f"Original Question: {state['contextualized_query']}\n\n"
            results_text += "No queries were executed. The system determined no SQL queries were needed.\n"

    return SubgraphOutput(
        main_context=results_text,
        cited_documents=[],
        response_metadata=response_metadata,
        subgraph_error=error_text,
    )


class SqlQueryExecutor:
    async def __call__(self, state: OrchestratorState) -> SubgraphOutput:
        return await _run_sql_query(state)
