# src/agents/shared/registry.py
from typing import Dict, List, Optional

from src.core.config.graph_configs import (
    DEEP_RESEARCH_CONFIG,
    DIRECT_RESPONSE_CONFIG,
    RAG_SEARCH_CONFIG,
    WEB_SEARCH_CONFIG,
)
from src.database.sql_database import AsyncSQLDatabase
from src.domain.entities.graph import SubgraphConfig
from src.domain.entities.state import SqlState


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
            "For quantitative data, metrics, counts, and aggregations."
        ),
        when_to_use=(
            "• Quantitative questions (how many, count, total, average)\n"
            "• Database structure questions (tables, columns, schema)\n"
            "• Data retrieval with filtering or conditions\n"
            "• Aggregations, rankings, or grouped statistics"
        ),
        examples=[
            "How many users signed up last month?",
            "What tables exist in the database?",
            "Show me all orders where status = 'pending'",
            "Average revenue by region",
            "Top 10 customers by purchase amount",
        ],
        query_indicators=[
            "how many",
            "count",
            "total",
            "average",
            "sum",
            "table",
            "database",
            "column",
            "show",
            "list",
            "top",
            "bottom",
            "group by",
            "where",
        ],
        not_suitable_for=[
            "conceptual database questions",
            "document searches",
            "web information",
        ],
        entry_state_type=SqlState,
        executor=executor,
    )
