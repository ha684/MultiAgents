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

        sections.append("# AVAILABLE SUBGRAPHS\n")
        sections.append(
            "Route user queries to the most appropriate subgraph based on their intent and needs.\n"
        )

        sorted_profiles = sorted(
            profiles.values(), key=lambda p: p.primary_behavior.priority, reverse=True
        )

        for profile in sorted_profiles:
            sections.append(f"\n## {profile.display_name}")
            sections.append(f"**Route Name:** `{profile.name}`\n")

            behavior = profile.primary_behavior
            sections.append("**Core Capability:**")
            sections.append(f"{behavior.action.capability}\n")

            sections.append("**When to Route Here:**")
            sections.append(f"{behavior.condition.trigger}")

            if behavior.condition.signals:
                sections.append(
                    f"\n**Signal Phrases:** {', '.join(behavior.condition.signals[:5])}"
                )

            if behavior.condition.exclude_when:
                sections.append(
                    f"\n**Do NOT route here if:** {' | '.join(behavior.condition.exclude_when)}"
                )

            sections.append("\n**Routing Guidance:**")
            sections.append(f"{behavior.action.router_instruction}")

            if profile.journeys:
                sections.append("\n**Typical User Flows:**")
                for journey in profile.journeys:
                    sections.append(f"- {journey.name}: {journey.description}")

            if profile.canonical_examples:
                sections.append("\n**Example Queries:**")
                for ex in profile.canonical_examples[:3]:
                    sections.append(f'  • "{ex["query"]}" → {ex["rationale"]}')

            sections.append("\n" + "-" * 60)

        return "\n".join(sections)

    @classmethod
    def _generate_compact_prompt(cls, profiles: dict[str, SubgraphProfile]) -> str:
        """Generate compact routing instructions for low-latency routing."""
        tools = []
        for name, profile in profiles.items():
            behavior = profile.primary_behavior
            tool_desc = f"{behavior.action.capability}\n"
            tool_desc += f"WHEN: {behavior.condition.trigger}\n"

            if behavior.condition.signals:
                tool_desc += f"SIGNALS: {', '.join(behavior.condition.signals[:5])}"

            tools.append({"name": name, "description": tool_desc})

        return tools

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


RAG_SEARCH_PROFILE = create_simple_subgraph(
    name="rag_search",
    display_name="Internal Knowledge Search",
    capability=(
        "Searches internal knowledge base using semantic search. "
        "Covers company docs, policies, procedures, and product documentation."
    ),
    trigger=(
        "User asks about internal/company-specific information, policies, "
        "procedures, or proprietary product features"
    ),
    signals=[
        "our policy",
        "our process",
        "our product",
        "our system",
        "company",
        "internal",
        "how do I",
        "how to",
        "documentation",
        "guide",
        "procedure",
        "onboarding",
        "employee handbook",
        "benefits",
        "PTO",
    ],
    router_instruction=(
        "Route user queries here when they need information from internal documentation. "
        "This includes: company policies, HR procedures, product documentation, "
        "internal tools/systems guides, and proprietary processes. "
        "\n\n"
        "DO NOT route here for:\n"
        "- External/public information (use web_search)\n"
        "- Database metrics/queries (use sql_query)\n"
        "- Current events or news (use web_search)\n"
        "\n"
        "When routing, ensure the query is clear and specific. "
        "If user asks vaguely like 'tell me about X', clarify what aspect they need."
    ),
    examples=[
        ("What is our refund policy?", "Direct policy question"),
        ("How do I submit a leave request?", "Internal HR process"),
        ("Explain our product's authentication flow", "Product technical docs"),
        ("What are the onboarding steps for new employees?", "HR documentation"),
        ("How does our CI/CD pipeline work?", "Internal system documentation"),
    ],
    exclude_when=[
        "asks about external/public information",
        "asks about current events or news after 2025",
        "asks for quantitative data or database queries",
        "asks about competitors or market information",
    ],
    executor="rag_search",
    entry_state_type=SimpleSearchState,
)

RAG_SEARCH_PROFILE.glossary = {
    "PTO": "Paid Time Off - vacation and sick leave policy",
    "OKR": "Objectives and Key Results - our goal-setting framework",
    "RFC": "Request for Comments - our technical proposal process",
    "Confluence": "Our internal wiki and documentation platform",
}

WEB_SEARCH_PROFILE = SubgraphProfile(
    name="web_search",
    display_name="Public Web Search",
    primary_behavior=SubgraphBehavior(
        condition=RoutingCondition(
            trigger=(
                "User asks about current events, external entities (competitors, industry), "
                "public information, or anything requiring up-to-date external data"
            ),
            signals=[
                "latest",
                "recent",
                "current",
                "news",
                "today",
                "competitor",
                "industry",
                "market",
                "trend",
                "regulation",
                "standard",
                "benchmark",
                "public",
                "what's new",
                "updates",
                "announcement",
            ],
            exclude_when=[
                "asks about internal company information",
                "asks for database metrics",
                "asks about proprietary data or processes",
            ],
        ),
        action=RoutingAction(
            capability=(
                "Searches public web for external information including "
                "news, industry data, competitors, regulations, and public knowledge"
            ),
            router_instruction=(
                "Route here when user needs external, public information that:\n"
                "• Has changed or might have changed recently\n"
                "• Is about entities outside our company (competitors, industry)\n"
                "• Requires current/live data (news, regulations, standards)\n"
                "• Is public knowledge not in our internal docs\n"
                "\n"
                "Transform vague queries into specific, searchable questions. "
                "For time-sensitive queries, include temporal context."
            ),
            expected_outcome="Current, externally-sourced information with proper citations",
        ),
        priority=50,
    ),
    canonical_examples=[
        {
            "query": "Latest AI developments in 2025",
            "rationale": "Current events and industry news",
        },
        {
            "query": "What did OpenAI announce last week?",
            "rationale": "Recent competitor news",
        },
        {
            "query": "Current GDPR requirements for data storage",
            "rationale": "Up-to-date regulatory information",
        },
        {
            "query": "Industry benchmark for SaaS churn rate",
            "rationale": "Public market data",
        },
    ],
    executor="web_search",
    entry_state_type=SimpleSearchState,
)

WEB_SEARCH_PROFILE.secondary_behaviors.append(
    SubgraphBehavior(
        condition=RoutingCondition(
            trigger="User asks to verify or fact-check information",
            signals=["is it true", "verify", "fact check", "confirm", "validate"],
        ),
        action=RoutingAction(
            capability="Verify claims using authoritative public sources",
            router_instruction="Use for fact-checking and verification of claims",
            expected_outcome="Verified information with source credibility assessment",
        ),
        priority=60,
    )
)

SQL_QUERY_PROFILE = SubgraphProfile(
    name="sql_query",
    display_name="Database Query Executor",
    primary_behavior=SubgraphBehavior(
        condition=RoutingCondition(
            trigger=(
                "User needs quantitative data, metrics, counts, or aggregations "
                "from structured databases"
            ),
            signals=[
                "how many",
                "count",
                "total",
                "average",
                "sum",
                "show me",
                "list",
                "top",
                "bottom",
                "rank",
                "table",
                "database",
                "column",
                "where",
                "group by",
                "order by",
                "filter",
                "query",
            ],
            requires_context={
                "needs_data_access": True,
            },
            exclude_when=[
                "asks conceptual questions about databases",
                "asks for document content or search",
                "needs external web information",
            ],
        ),
        action=RoutingAction(
            capability=(
                "Executes SQL queries against structured databases. "
                "Provides quantitative answers, data retrieval, aggregations, and analytics."
            ),
            router_instruction=(
                "Route here for questions that require querying databases:\n"
                "• Counting/summing/averaging (how many users, total revenue)\n"
                "• Data retrieval with filters (show orders where status='pending')\n"
                "• Rankings and aggregations (top customers, average by region)\n"
                "• Schema exploration (what tables exist, show columns)\n"
                "\n"
                "Important:\n"
                "- Ensure user query is specific about what data they need\n"
                "- For vague queries, may need to ask clarifying questions first\n"
                "- Extract clear data requirements before delegating\n"
            ),
            expected_outcome="Structured data results with insights and context",
            query_transformation=(
                "Transform natural language query into clear data requirement: "
                "What to retrieve, from where, with what conditions, how to aggregate"
            ),
        ),
        priority=70,
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
            "query": "How many users signed up last month?",
            "rationale": "Simple count with time filter → Simple Retrieval",
        },
        {
            "query": "Show top 10 customers by purchase amount",
            "rationale": "Ranked aggregation → Simple Retrieval",
        },
        {
            "query": "What tables exist in the database?",
            "rationale": "Schema exploration → Simple Retrieval",
        },
        {
            "query": "Analyze sales trends by region over last year",
            "rationale": "Pattern analysis over time → Exploratory Analysis",
        },
        {
            "query": "Give me a monthly revenue report with breakdowns",
            "rationale": "Multiple metrics, formatted output → Report Generation",
        },
    ],
    entry_state_type=SqlState,
    executor=None,
    tags=["data", "analytics", "quantitative"],
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
    SubgraphRegistry.register(SQL_QUERY_PROFILE)


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

    sql_profile = SubgraphRegistry.get_profile("sql_query")
    if sql_profile:
        sql_profile.executor = executor
        if hasattr(sql_db, "get_table_info"):
            pass

    return sql_profile
