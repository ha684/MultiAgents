# src/agents/subgraphs/sql_factory.py
from src.database.sql_database import AsyncSQLDatabase
from src.domain.entities.graph import SubgraphConfig
from src.agents.executors.sql_query import SqlQueryExecutor
from src.agents.graph.state import SqlState


def make_sql_subgraph(db_url: str, allow_tables: list[str]) -> SubgraphConfig:
    sql_db = AsyncSQLDatabase.from_uri(
        database_uri=db_url,
        sample_rows_in_table_info=3,
        include_tables=allow_tables,
    )
    executor = SqlQueryExecutor(sql_db)

    return SubgraphConfig(
        name="sql_query",
        description=(
            "Executes SQL queries against structured databases. "
            "Handles queries about database structure (tables, columns, schemas) "
            "and data retrieval (metrics, counts, aggregations, filtering)."
        ),
        when_to_use=(
            "Use when query asks about:\n"
            "• Database structure: table existence, available tables, column schemas\n"
            "• Quantitative data: counts, totals, averages, sums, metrics\n"
            "• Data lists: retrieving records, filtering by criteria\n"
            "• Aggregations: grouping, ranking, top N, breakdowns"
        ),
        examples=[
            "Bảng conversations có tồn tại trong hệ thống không?",
            "Does the users table exist?",
            "What tables are in the database?",
            "Show me columns in the orders table",
            "How many users signed up last month?",
            "List all active customers",
            "Count failed transactions today",
            "Average order value by region",
            "Top 10 products by revenue",
            "Get users where country = 'Vietnam'",
        ],
        query_indicators=[
            # Structure queries
            "table",
            "database",
            "schema",
            "column",
            "exist",
            "available",
            # Quantitative queries
            "how many",
            "count",
            "number of",
            "total",
            "sum",
            "average",
            "mean",
            "max",
            "min",
            "median",
            # Data retrieval
            "show",
            "list",
            "get",
            "retrieve",
            "fetch",
            "display",
            "all",
            "where",
            "filter",
            "by",
            # Aggregations
            "group by",
            "top",
            "bottom",
            "rank",
            "breakdown",
        ],
        not_suitable_for=[
            "conceptual questions about databases (e.g., 'what is SQL?')",
            "document-based information searches",
            "external web data",
            "unstructured text analysis",
        ],
        entry_state_type=SqlState,
        executor=executor,
        fallback_chain=["rag_search"],
        requires_confirmation=False,
    )
