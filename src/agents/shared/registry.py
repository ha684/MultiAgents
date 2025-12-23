# src/agents/shared/registry.py
from typing import Literal

from src.database.sql_database import AsyncSQLDatabase
from src.domain.entities.graph import (
    RoutingAction,
    RoutingCondition,
    SubgraphBehavior,
    SubgraphExecutor,
    SubgraphJourney,
    SubgraphProfile,
)
from src.domain.entities.state import SimpleSearchState, SqlState


class SubgraphRegistry:
    """
    Enhanced registry with Parlant-inspired design principles.
    """

    _profiles: dict[str, SubgraphProfile] = {}

    @classmethod
    def register(cls, profile: SubgraphProfile):
        """Register a subgraph profile."""
        cls._profiles[profile.name] = profile

    @classmethod
    def unregister(cls, name: str):
        """Remove a subgraph profile."""
        cls._profiles.pop(name, None)

    @classmethod
    def get_profile(cls, name: str) -> SubgraphProfile | None:
        """Get a specific profile."""
        return cls._profiles.get(name)

    @classmethod
    def resolve_active(
        cls,
        allow: list[str] | None = None,
        block: list[str] | None = None,
        extras: dict[str, SubgraphProfile] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, SubgraphProfile]:
        """
        Resolve active subgraphs with filtering.
        Similar to Parlant's dynamic context management.
        """
        base = dict(cls._profiles)

        if extras:
            base.update(extras)

        if tags:
            base = {k: v for k, v in base.items() if any(tag in v.tags for tag in tags)}

        if allow:
            base = {k: v for k, v in base.items() if k in set(allow)}

        if block:
            for b in block:
                base.pop(b, None)

        if "direct_response" not in base and "direct_response" in cls._profiles:
            base["direct_response"] = cls._profiles["direct_response"]

        return base

    @classmethod
    def generate_routing_prompt(
        cls,
        active_profiles: dict[str, SubgraphProfile],
        format: Literal["detailed", "compact"] = "detailed",
    ) -> str:
        """
        Generate dynamic routing instructions for LLM.
        Only includes relevant information based on context.
        """
        if format == "compact":
            return cls._generate_compact_prompt(active_profiles)
        return cls._generate_detailed_prompt(active_profiles)

    @classmethod
    def _generate_detailed_prompt(
        cls,
        profiles: dict[str, SubgraphProfile],
    ) -> str:
        """Generate detailed routing instructions."""
        sections = []

        sections.append("AVAILABLE TOOLS")
        sections.append(
            "\nYou must select exactly ONE tool from this list based on user intent. "
            "Use the exact name shown in [ROUTE NAME].\n"
        )
        sections.append(
            "Each tool serves a DIFFERENT purpose - choose based on WHAT the user needs:\n"
        )

        sorted_profiles = sorted(profiles.values(), key=lambda p: p.name)

        for i, profile in enumerate(sorted_profiles, 1):
            sections.append(f"[{i}] {profile.display_name}")
            sections.append(f"[ROUTE NAME]: {profile.name}")
            sections.append("")

            behavior = profile.primary_behavior

            sections.append("CAPABILITY:")
            sections.append(f"   {behavior.action.capability}")
            sections.append("")

            sections.append("WHEN TO USE THIS TOOL:")
            sections.append(f"   {behavior.condition.trigger}")
            sections.append("")

            if behavior.condition.signals:
                sections.append("SIGNAL KEYWORDS:")
                signals_str = ", ".join(
                    f'"{s}"' for s in behavior.condition.signals[:8]
                )
                sections.append(f"   {signals_str}")
                if len(behavior.condition.signals) > 8:
                    sections.append(
                        f"   ...and {len(behavior.condition.signals) - 8} more"
                    )
                sections.append("")

            sections.append("ROUTING INSTRUCTION:")
            sections.append(f"   {behavior.action.router_instruction}")
            sections.append("")

            if behavior.condition.exclude_when:
                sections.append("DO NOT USE IF:")
                for exclude in behavior.condition.exclude_when:
                    sections.append(f"   • {exclude}")
                sections.append("")

            if profile.canonical_examples:
                sections.append("EXAMPLE QUERIES:")
                for ex in profile.canonical_examples[:3]:
                    sections.append(f'   ✓ "{ex["query"]}"')
                    sections.append(f"     → {ex['rationale']}")
                sections.append("")

        sections.append("\n")
        sections.append("SELECTION RULES")
        sections.append("1. You MUST choose exactly ONE subgraph from the list above")
        sections.append("2. Use the exact [ROUTE NAME] value")
        sections.append("3. Match user intent to the tool's CAPABILITY and WHEN TO USE")
        sections.append("4. Check SIGNAL KEYWORDS for quick pattern matching")
        sections.append("5. Avoid tools with matching DO NOT USE conditions")

        return "\n".join(sections)

    @classmethod
    def _generate_compact_prompt(cls, profiles: dict[str, SubgraphProfile]) -> str:
        """Generate compact routing instructions for low-latency routing."""
        lines = ["AVAILABLE TOOLS:\n"]

        for name, profile in profiles.items():
            behavior = profile.primary_behavior
            lines.append(f"• {name}:")
            lines.append(f"  - {behavior.action.capability}")
            lines.append(f"  - When: {behavior.condition.trigger}")
            if behavior.condition.signals:
                lines.append(
                    f"  - Keywords: {', '.join(behavior.condition.signals[:5])}"
                )
            lines.append("")

        lines.append("\nYou MUST select one tool name from the list above.")
        return "\n".join(lines)

    @classmethod
    def generate_capability_summary(
        cls,
        active_profiles: dict[str, SubgraphProfile] | None = None,
    ) -> str:
        """
        Generate a brief capability summary for verification agent.

        This is NOT for tool selection (that's routing prompt).
        This is for the verification agent to know what the system CAN do,
        so it can accurately assess if information gaps are fillable.

        Args:
            active_profiles: If provided, use these. Otherwise use all registered profiles.

        Returns:
            A concise summary of system capabilities (not routing instructions).
        """
        profiles = active_profiles or cls._profiles

        if not profiles:
            return "No tools currently available."

        lines = ["This system has access to the following capabilities:"]
        lines.append("")

        for name, profile in sorted(profiles.items(), key=lambda x: x[0]):
            behavior = profile.primary_behavior
            # Just the capability, no routing instructions
            lines.append(f"• **{profile.display_name}** ({name}):")
            lines.append(f"  {behavior.action.capability}")
            lines.append("")

        lines.append(
            "When evaluating if information is obtainable, consider these actual capabilities."
        )
        lines.append(
            "Do NOT assume limitations that don't exist - check if a capability above could address the need."
        )

        return "\n".join(lines)

    @classmethod
    def get_subgraph_executor(
        cls,
        name: str,
        active_map: dict[str, SubgraphProfile],
    ) -> SubgraphExecutor | None:
        """Get executor for a subgraph."""
        profile = active_map.get(name)
        return profile.executor if profile else None


def create_simple_subgraph(
    name: str,
    display_name: str,
    capability: str,
    trigger: str,
    signals: list[str],
    router_instruction: str,
    examples: list[tuple[str, str]],
    exclude_when: list[str] | None = None,
    executor: any = None,
    entry_state_type: type | None = None,
) -> SubgraphProfile:
    """
    Helper to create a simple subgraph profile.
    For backward compatibility with existing configs.
    """
    return SubgraphProfile(
        name=name,
        display_name=display_name,
        primary_behavior=SubgraphBehavior(
            condition=RoutingCondition(
                trigger=trigger,
                signals=signals,
                exclude_when=exclude_when or [],
            ),
            action=RoutingAction(
                capability=capability,
                router_instruction=router_instruction,
                expected_outcome=f"User query handled via {name}",
            ),
        ),
        canonical_examples=[{"query": q, "rationale": r} for q, r in examples],
        executor=executor,
        entry_state_type=entry_state_type,
    )


def create_journey_subgraph(
    name: str,
    display_name: str,
    capability: str,
    trigger: str,
    signals: list[str],
    router_instruction: str,
    journey_name: str,
    journey_description: str,
    flow_steps: list[str],
    examples: list[tuple[str, str]],
    executor: any = None,
    entry_state_type: type | None = None,
) -> SubgraphProfile:
    """
    Helper to create a subgraph with a defined journey.
    Use for complex multi-step processes.
    """
    profile = create_simple_subgraph(
        name=name,
        display_name=display_name,
        capability=capability,
        trigger=trigger,
        signals=signals,
        router_instruction=router_instruction,
        examples=examples,
        executor=executor,
        entry_state_type=entry_state_type,
    )

    profile.journeys.append(
        SubgraphJourney(
            name=journey_name,
            description=journey_description,
            activation_conditions=[trigger],
            typical_flow=flow_steps,
        )
    )

    return profile


RAG_SEARCH_PROFILE = SubgraphProfile(
    name="rag_search",
    display_name="Document Search (Unstructured Data)",
    primary_behavior=SubgraphBehavior(
        condition=RoutingCondition(
            trigger=(
                "User asks questions about information, concepts, or any unstructured content. "
                "PRIMARY and DEFAULT choice unless query explicitly needs real-time data or database records."
            ),
            signals=[
                "tìm",
                "search",
                "thông tin",
                "information",
                "what is",
                "explain",
                "how to",
                "why",
            ],
            exclude_when=[
                "Query explicitly needs CURRENT/REAL-TIME data: 'hôm nay', 'today', 'hiện tại', 'now'",
                "Query needs LIVE data: weather, stock prices, exchange rates",
                "Query needs STRUCTURED DATABASE records: counts, totals, lists from tables",
            ],
        ),
        action=RoutingAction(
            capability=(
                "Searches through documents and knowledge base using semantic search. "
                "PRIMARY tool for information retrieval and general questions."
            ),
            router_instruction=(
                "Use as DEFAULT for:\n"
                "• General questions and information requests\n"
                "• Conceptual questions, explanations\n"
                "• Finding information from documents\n"
                "\n"
                "Skip ONLY if:\n"
                "• Needs real-time/live data (weather, prices, current events)\n"
                "• Needs structured database queries (counts, records, tables)"
            ),
            expected_outcome="Relevant information from knowledge base",
        ),
    ),
    canonical_examples=[
        {
            "query": "tìm thông tin về LMM counting errors",
            "rationale": "General information request - use RAG",
        },
        {
            "query": "Giải thích cách hoạt động của transformer",
            "rationale": "Conceptual question - use RAG",
        },
    ],
    executor="rag_search",
    entry_state_type=SimpleSearchState,
    tags=["vector", "semantic", "documents", "unstructured", "primary", "default"],
)

RAG_SEARCH_PROFILE.secondary_behaviors.append(
    SubgraphBehavior(
        condition=RoutingCondition(
            trigger="User asks follow-up questions about previously retrieved documents",
            signals=["tell me more", "elaborate", "from that document", "in that file"],
        ),
        action=RoutingAction(
            capability="Deep dive into specific topics from vector database",
            router_instruction="Continue searching vector DB for related content",
            expected_outcome="More detailed information from stored documents",
        ),
    )
)

WEB_SEARCH_PROFILE = SubgraphProfile(
    name="web_search",
    display_name="Internet Web Search",
    primary_behavior=SubgraphBehavior(
        condition=RoutingCondition(
            trigger=(
                "Query needs current/live external data, general world knowledge, "
                "or information clearly outside the organization's domain."
            ),
            signals=[
                "hôm nay",
                "today",
                "hiện tại",
                "current",
                "mới nhất",
                "latest",
                "thời tiết",
                "weather",
                "giá",
                "price",
                "tỷ giá",
                "exchange rate",
            ],
            exclude_when=[
                "Query about internal work, projects, or organizational content",
                "Query mentions specific internal entities (project names, internal IDs, colleague names)",
                "Historical/past information that wouldn't change",
            ],
        ),
        action=RoutingAction(
            capability=(
                "Searches public internet for up-to-date external information. "
                "Best for current events, general knowledge, and real-time data."
            ),
            router_instruction=(
                "Use when query needs:\n"
                "• Real-time data: weather, stock prices, exchange rates, live scores\n"
                "• Current events: today's news, recent announcements\n"
                "• General world knowledge: famous people, countries, public facts\n"
                "• External companies/products: competitors, public organizations\n"
                "• Programming syntax, libraries, public documentation\n"
                "\n"
                "Skip for internal/organizational content."
            ),
            expected_outcome="Web search results from internet sources",
        ),
    ),
    canonical_examples=[
        {
            "query": "thời tiết Hà Nội hôm nay",
            "rationale": "Real-time weather data",
        },
        {
            "query": "What are the latest AI developments?",
            "rationale": "Current events and trends",
        },
        {
            "query": "How to use React hooks?",
            "rationale": "Public programming knowledge",
        },
    ],
    executor="web_search",
    entry_state_type=SimpleSearchState,
    tags=["internet", "web", "external", "realtime"],
)

WEB_SEARCH_PROFILE.secondary_behaviors.append(
    SubgraphBehavior(
        condition=RoutingCondition(
            trigger="User asks follow-up questions about web search results",
            signals=["more about that", "from that website", "similar articles"],
        ),
        action=RoutingAction(
            capability="Continue searching the web for related information",
            router_instruction="Perform additional web searches for follow-up",
            expected_outcome="Additional web results related to previous search",
        ),
    )
)

SQL_QUERY_PROFILE = SubgraphProfile(
    name="sql_query",
    display_name="PostgreSQL Database Query (Structured Data)",
    primary_behavior=SubgraphBehavior(
        condition=RoutingCondition(
            trigger=(
                "User wants to query STRUCTURED DATA from PostgreSQL database tables - "
                "records, counts, statistics, aggregations, or any tabular data"
            ),
            signals=[
                "how many",
                "count",
                "total",
                "average",
                "sum",
                "list all",
                "show records",
                "get data",
                "users table",
                "orders table",
                "database records",
                "filter by",
                "group by",
                "statistics",
                "top 10",
                "recent orders",
                "active users",
            ],
            requires_context={
                "needs_data_access": True,
            },
            exclude_when=[
                "User wants to search for documents or text content",
                "User wants to search the internet for external information",
                "User asks conceptual questions (not requesting actual data)",
            ],
        ),
        action=RoutingAction(
            capability=(
                "Executes SQL queries against POSTGRESQL database tables. "
                "Retrieves structured records, performs counts, aggregations, "
                "filtering, and analytics on tabular data (users, orders, products, etc.)."
            ),
            router_instruction=(
                "Use this tool when:\n"
                "• User needs data from DATABASE TABLES (users, orders, products, etc.)\n"
                "• Asking for counts, totals, averages, or statistics\n"
                "• Wants to list/filter/sort structured records\n"
                "• Needs to query specific columns or apply conditions\n"
                "• Asks about database schema (tables, columns)\n"
            ),
            expected_outcome="Query results from PostgreSQL tables with data rows and aggregations",
            query_transformation=(
                "Transform natural language into SQL query requirements: "
                "tables, columns, conditions, aggregations, sorting"
            ),
        ),
    ),
    journeys=[
        SubgraphJourney(
            name="Simple Data Retrieval",
            description="Direct query for specific data points or lists",
            activation_conditions=[
                "User asks for specific count, value, or list",
                "Query is straightforward with clear data target",
            ],
            typical_flow=[
                "Understand what data is needed",
                "Identify table and columns",
                "Apply any filters or conditions",
                "Execute query",
                "Present results clearly",
            ],
            prerequisites=["Database access available", "Clear data requirement"],
        ),
        SubgraphJourney(
            name="Exploratory Analysis",
            description="Multi-step investigation of data patterns and insights",
            activation_conditions=[
                "User wants to explore data without specific question",
                "Asks about trends, patterns, or anomalies",
            ],
            typical_flow=[
                "Understand analytical goal",
                "Explore schema and available data",
                "Query initial data for overview",
                "Identify interesting patterns",
                "Drill down into specifics",
                "Summarize insights",
            ],
            digression_patterns={
                "user adds filter": "Incorporate new filter and re-query",
                "user changes metric": "Adjust aggregation and recalculate",
                "user asks for comparison": "Query comparison data and present side-by-side",
            },
            prerequisites=["User has exploratory intent", "Sufficient data exists"],
        ),
        SubgraphJourney(
            name="Report Generation",
            description="Create formatted report with multiple metrics",
            activation_conditions=[
                "User asks for report, summary, or dashboard",
                "Needs multiple related metrics together",
            ],
            typical_flow=[
                "Identify all required metrics",
                "Plan efficient queries (avoid N+1)",
                "Execute queries in optimal order",
                "Format results cohesively",
                "Add context and interpretations",
                "Offer export or further analysis",
            ],
            prerequisites=["Clear report scope", "Multiple related metrics"],
        ),
    ],
    canonical_examples=[
        {
            "query": "How many users registered last month?",
            "rationale": "Count query on users table with date filter",
        },
        {
            "query": "Show me all orders with status pending",
            "rationale": "Select records from orders table with condition",
        },
        {
            "query": "What is the total revenue this quarter?",
            "rationale": "Aggregation (SUM) on transaction data",
        },
        {
            "query": "List top 10 customers by purchase amount",
            "rationale": "Ranked query with aggregation and limit",
        },
        {
            "query": "What tables are in the database?",
            "rationale": "Schema exploration query",
        },
    ],
    entry_state_type=SqlState,
    executor=None,
    tags=["postgresql", "sql", "database", "structured"],
)

SQL_QUERY_PROFILE.glossary = {
    "users": "Main user accounts table with profile information",
    "orders": "Transaction records with order details",
    "customers": "Customer business profiles and metadata",
    "products": "Product catalog with pricing and inventory",
    "events": "User activity event log",
}


def seed_base_subgraphs():
    """
    Populate registry with all base subgraph profiles.
    Call this on application startup.
    """
    SubgraphRegistry.register(RAG_SEARCH_PROFILE)
    SubgraphRegistry.register(WEB_SEARCH_PROFILE)


def enable_sql(db_url: str, allow_tables: list[str]):
    """
    Enable SQL subgraph with database connection.
    Returns the configured profile.
    """
    from src.agents.executors.sql_query import SqlQueryExecutor

    sql_db = AsyncSQLDatabase.from_uri(
        database_uri=db_url,
        sample_rows_in_table_info=3,
        include_tables=allow_tables,
    )
    executor = SqlQueryExecutor(sql_db)
    SubgraphRegistry.register(SQL_QUERY_PROFILE)
    sql_profile = SubgraphRegistry.get_profile("sql_query")
    if sql_profile:
        sql_profile.executor = executor
        if hasattr(sql_db, "get_table_info"):
            pass

    return sql_profile
