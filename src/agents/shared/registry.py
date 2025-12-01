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

        sections.append("AVAILABLE SUBGRAPHS (Tools for Information Retrieval)")
        sections.append(
            "\nYou must select ONE subgraph from this list. "
            "Use the exact name shown in [ROUTE NAME].\n"
        )

        sorted_profiles = sorted(
            profiles.values(), key=lambda p: p.primary_behavior.priority, reverse=True
        )

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
    display_name="Knowledge Base Search",
    primary_behavior=SubgraphBehavior(
        condition=RoutingCondition(
            trigger=(
                "User asks questions that could be answered from stored knowledge - "
                "documents, articles, guides, references, or any ingested content"
            ),
            signals=[
                "how to",
                "how do I",
                "what is",
                "explain",
                "guide",
                "documentation",
                "steps",
                "process",
                "procedure",
                "about",
                "describe",
                "definition",
                "overview",
                "tutorial",
                "example",
                "best practice",
            ],
            exclude_when=[
                "explicitly asks for 'latest' or 'recent' or 'current' information",
                "asks for quantitative data or database queries (use sql_query)",
                "asks to verify breaking news or very recent events (within days)",
            ],
        ),
        action=RoutingAction(
            capability=(
                "Searches knowledge base containing ingested documents and content. "
                "This could be anything previously stored: articles, guides, research papers, "
                "product docs, policies, procedures, tutorials, references, or domain knowledge."
            ),
            router_instruction=(
                "Route here as PRIMARY choice when:\n"
                "• User asks informational questions that could be answered from documents\n"
                "• Query is about concepts, processes, or explanations\n"
                "• Looking for guides, tutorials, or how-to information\n"
                "• Needs domain knowledge or reference material\n"
                "• Asks about things that might be documented\n"
                "\n"
                "PREFER this over web_search UNLESS:\n"
                "• User explicitly needs 'latest/recent/current' information\n"
                "• Query is clearly about breaking news or very recent events\n"
                "• Asks to verify current status of external entities\n"
                "\n"
                "Philosophy: Try knowledge base first for informational queries. "
                "Web search is for verified recency needs."
            ),
            expected_outcome="Relevant information from stored knowledge with source references",
        ),
        priority=80,  # Higher than web_search for general informational queries
    ),
    canonical_examples=[
        {
            "query": "How does OAuth 2.0 work?",
            "rationale": "Technical concept likely documented in knowledge base",
        },
        {
            "query": "What are best practices for API design?",
            "rationale": "Domain knowledge and guidelines",
        },
        {
            "query": "Explain the refund policy",
            "rationale": "Policy documentation",
        },
        {
            "query": "How do I reset my password?",
            "rationale": "Procedural guide likely in docs",
        },
        {
            "query": "What is machine learning?",
            "rationale": "Conceptual explanation, may be in knowledge base",
        },
        {
            "query": "Show me examples of good code reviews",
            "rationale": "Reference material and best practices",
        },
    ],
    executor="rag_search",
    entry_state_type=SimpleSearchState,
    tags=["knowledge", "documents", "reference"],
)

RAG_SEARCH_PROFILE.secondary_behaviors.append(
    SubgraphBehavior(
        condition=RoutingCondition(
            trigger="User asks follow-up questions after getting knowledge base results",
            signals=["tell me more", "elaborate", "give me details", "explain further"],
        ),
        action=RoutingAction(
            capability="Deep dive into specific topics from knowledge base",
            router_instruction="Continue using knowledge base for follow-up deep dives",
            expected_outcome="More detailed information on specific aspects",
        ),
        priority=85,
    )
)

WEB_SEARCH_PROFILE = SubgraphProfile(
    name="web_search",
    display_name="Public Web Search",
    primary_behavior=SubgraphBehavior(
        condition=RoutingCondition(
            trigger=(
                "User explicitly needs current/latest/recent information, "
                "breaking news, real-time data, or verification of very recent events"
            ),
            signals=[
                "latest",
                "recent",
                "current",
                "today",
                "this week",
                "this month",
                "breaking",
                "just announced",
                "newest",
                "up-to-date",
                "right now",
                "as of",
                "updated",
            ],
            exclude_when=[
                "asks for quantitative database metrics (use sql_query)",
                "general informational query without recency requirement (try rag_search first)",
            ],
        ),
        action=RoutingAction(
            capability=(
                "Searches public web for real-time information, recent updates, "
                "breaking news, and current status verification"
            ),
            router_instruction=(
                "Route here when user EXPLICITLY needs:\n"
                "• Latest/current/recent information (temporal keywords present)\n"
                "• Breaking news or events from past few days/weeks\n"
                '• Verification of current status ("is X still CEO?", "did Y happen?")\n'
                "• Real-time data (stock prices, weather, live scores)\n"
                "• Updates or announcements specifically mentioned as recent\n"
                "\n"
                "DO NOT route here for:\n"
                "• General informational questions without recency needs\n"
                "• Conceptual or how-to questions (prefer rag_search)\n"
                "• Historical facts or established knowledge\n"
                "\n"
                "Transform vague queries into specific, time-aware search questions."
            ),
            expected_outcome="Current information with timestamps and source credibility",
        ),
        priority=70,  # Lower than rag_search for general queries, high for recency
    ),
    canonical_examples=[
        {
            "query": "Latest AI developments in 2025",
            "rationale": "Explicit 'latest' keyword - needs current information",
        },
        {
            "query": "What did OpenAI announce this week?",
            "rationale": "Recent announcement with temporal context",
        },
        {
            "query": "Current GDPR requirements",
            "rationale": "'Current' indicates need for up-to-date regulatory info",
        },
        {
            "query": "Is Elon Musk still CEO of Tesla?",
            "rationale": "Verification of current status",
        },
        {
            "query": "News about recent tech layoffs",
            "rationale": "Breaking news query",
        },
        {
            "query": "What's the weather today?",
            "rationale": "Real-time data need",
        },
    ],
    executor="web_search",
    entry_state_type=SimpleSearchState,
    tags=["web", "current", "external", "real-time"],
)

WEB_SEARCH_PROFILE.secondary_behaviors.append(
    SubgraphBehavior(
        condition=RoutingCondition(
            trigger="User asks about external entities when knowledge base returns insufficient results",
            signals=["competitor", "company", "organization", "market", "industry"],
        ),
        action=RoutingAction(
            capability="Fallback for external entity information not in knowledge base",
            router_instruction="Use as fallback when RAG doesn't have external entity info",
            expected_outcome="Public information about external entities",
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
