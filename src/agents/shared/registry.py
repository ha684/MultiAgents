# src/agents/shared/registry.py
from typing import Dict, List, Optional

from src.core.config.graph_configs import (
    DEEP_RESEARCH_CONFIG,
    DIRECT_RESPONSE_CONFIG,
    RAG_SEARCH_CONFIG,
    WEB_SEARCH_CONFIG,
)
from src.domain.entities.graph import SubgraphConfig
from src.domain.entities.state import SqlState
from src.database.sql_database import AsyncSQLDatabase


class SubgraphRegistry:
    _subgraphs: Dict[str, SubgraphConfig] = {}

    @classmethod
    def register(cls, config: SubgraphConfig):
        cls._subgraphs[config.name] = config

    @classmethod
    def unregister(cls, name: str):
        cls._subgraphs.pop(name, None)

    @classmethod
    def resolve_active(
        cls,
        allow: Optional[List[str]] = None,
        block: Optional[List[str]] = None,
        extras: Optional[Dict[str, SubgraphConfig]] = None,
    ) -> Dict[str, SubgraphConfig]:
        base = dict(cls._subgraphs)
        if extras:
            base.update(extras)

        if allow:
            base = {k: v for k, v in base.items() if k in set(allow)}

        if block:
            for b in block:
                base.pop(b, None)

        if "direct_response" not in base and "direct_response" in cls._subgraphs:
            base["direct_response"] = cls._subgraphs["direct_response"]

        return base

    @classmethod
    def definitions_from_map(cls, m: Dict[str, SubgraphConfig]) -> List[Dict]:
        tools = []
        for name, config in m.items():
            tool_desc = f"**{name.upper()}**\n\n{config.description}"
            tool_desc += f"\n\n**When to use:**\n{config.when_to_use}"
            if config.examples:
                tool_desc += "\n\n**Example queries:**" + "".join(
                    f"\n  • {ex}" for ex in config.examples[:3]
                )
            if config.query_indicators:
                tool_desc += (
                    f"\n\n**Keyword indicators:** {', '.join(config.query_indicators)}"
                )
            if config.not_suitable_for:
                tool_desc += (
                    f"\n\n**NOT suitable for:** {', '.join(config.not_suitable_for)}"
                )
            tools.append({"name": name, "description": tool_desc})
        return tools

    @classmethod
    def get_subgraph_active(
        cls,
        name: str,
        active_map: Dict[str, SubgraphConfig],
    ) -> Optional[SubgraphConfig]:
        return active_map.get(name)


def seed_base_subgraphs():
    SubgraphRegistry.register(RAG_SEARCH_CONFIG)
    SubgraphRegistry.register(WEB_SEARCH_CONFIG)
    SubgraphRegistry.register(DEEP_RESEARCH_CONFIG)
    SubgraphRegistry.register(DIRECT_RESPONSE_CONFIG)


def enable_sql(db_url: str, allow_tables: list[str]):
    sql_cfg = make_sql_subgraph(db_url, allow_tables)
    return sql_cfg


def make_sql_subgraph(db_url: str, allow_tables: list[str]) -> SubgraphConfig:
    from src.agents.executors.sql_query import SqlQueryExecutor

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
