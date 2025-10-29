# src/agents/shared/registry.py
from typing import Dict, List, Optional

from src.agents.graph.state import ResearchState, SimpleSearchState, SqlState
from src.domain.entities.graph import SubgraphConfig


class SubgraphRegistry:
    """Central registry for all subgraphs"""

    _subgraphs: Dict[str, SubgraphConfig] = {}

    @classmethod
    def register(cls, config: SubgraphConfig):
        """Register a subgraph"""
        cls._subgraphs[config.name] = config

    @classmethod
    def get_definitions(cls) -> List[Dict]:
        """Convert subgraphs to tool definitions for router"""
        tools = []
        for name, config in cls._subgraphs.items():
            tool_desc = f"**{name.upper()}**\n\n{config.description}"

            tool_desc += f"\n\n**When to use:**\n{config.when_to_use}"

            if config.examples:
                tool_desc += "\n\n**Example queries:**"
                for ex in config.examples[:3]:
                    tool_desc += f"\n  • {ex}"

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
    def get_subgraph(cls, name: str) -> Optional[SubgraphConfig]:
        """Get subgraph config"""
        return cls._subgraphs.get(name)


SubgraphRegistry.register(
    SubgraphConfig(
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
        executor="sql_query",
        fallback_chain=["rag_search"],
        requires_confirmation=False,
    )
)

SubgraphRegistry.register(
    SubgraphConfig(
        name="rag_search",
        description=(
            "Searches internal knowledge base and documentation. "
            "Retrieves information from company documents, policies, procedures, "
            "and product documentation using semantic search."
        ),
        when_to_use=(
            "Use when query asks about:\n"
            "• Company policies, procedures, guidelines, rules\n"
            "• Product documentation, features, capabilities, specifications\n"
            "• How-to guides, instructions, processes, workflows\n"
            "• Internal knowledge, historical information, FAQs"
        ),
        examples=[
            "What is the company's revenue recognition policy?",
            "How do I reset my password?",
            "What are our office hours?",
            "Explain the key features of our product",
            "What's the procedure for requesting leave?",
            "How does our authentication system work?",
            "Employee benefits overview",
            "Onboarding process for new hires",
        ],
        query_indicators=[
            # Policies and procedures
            "policy",
            "procedure",
            "guideline",
            "rule",
            "process",
            "protocol",
            "standard operating procedure",
            # Documentation
            "documentation",
            "manual",
            "guide",
            "instructions",
            "how to",
            "how do I",
            "steps to",
            "way to",
            # Internal knowledge
            "company",
            "our",
            "internal",
            "employee",
            "what is our",
            "explain our",
            "describe our",
            # Product info
            "product",
            "feature",
            "capability",
            "functionality",
        ],
        not_suitable_for=[
            "quantitative database queries",
            "current events or recent news",
            "external public information",
            "real-time data",
        ],
        entry_state_type=SimpleSearchState,
        executor="rag_search",
        fallback_chain=["web_search", "deep_research"],
        requires_confirmation=False,
    )
)

SubgraphRegistry.register(
    SubgraphConfig(
        name="web_search",
        description=(
            "Searches the public web for external information. "
            "Retrieves current events, news, industry trends, competitor information, "
            "standards, regulations, and publicly available data."
        ),
        when_to_use=(
            "Use when query asks about:\n"
            "• Current events, recent news, latest updates, trends\n"
            "• External entities: competitors, industry, market, public companies\n"
            "• Public standards, regulations, certifications, compliance\n"
            "• Time-sensitive information that may have changed recently"
        ),
        examples=[
            "Latest changes to ISO 27001 in 2025",
            "Recent news about Competitor X's product launch",
            "Current industry benchmark for customer churn",
            "Latest AI developments in healthcare",
            "New GDPR requirements this year",
            "Market trends in SaaS pricing",
            "Competitor Y's recent earnings report",
        ],
        query_indicators=[
            # Temporal
            "latest",
            "recent",
            "current",
            "new",
            "updated",
            "today",
            "this week",
            "this month",
            "this year",
            "2025",
            "now",
            "nowadays",
            "currently",
            # External entities
            "competitor",
            "competitors",
            "industry",
            "market",
            "company X",
            "business Y",
            "vendor",
            # Public info
            "news",
            "announcement",
            "press release",
            "report",
            "trend",
            "benchmark",
            "standard",
            "regulation",
            "ISO",
            "GDPR",
            "compliance",
            "certification",
        ],
        not_suitable_for=[
            "internal company information",
            "database queries or metrics",
            "proprietary data",
        ],
        entry_state_type=SimpleSearchState,
        executor="web_search",
        fallback_chain=["rag_search", "deep_research"],
        requires_confirmation=False,
    )
)

SubgraphRegistry.register(
    SubgraphConfig(
        name="deep_research",
        description=(
            "Conducts multi-step iterative research with adaptive strategy. "
            "Performs comprehensive analysis requiring multiple information sources, "
            "synthesis, and strategic reasoning. Suitable for complex, open-ended questions."
        ),
        when_to_use=(
            "Use when query requires:\n"
            "• Exploratory investigation where answer path is unclear\n"
            "• Multiple iterations of search and synthesis\n"
            "• Comprehensive analysis combining multiple sources\n"
            "• Strategic recommendations or evaluations\n"
            "• Root cause analysis or deep investigation"
        ),
        examples=[
            "Research emerging AI trends and their impact on our industry",
            "Investigate why sales dropped last quarter and recommend solutions",
            "What should our market expansion strategy be for next year?",
            "Explore cloud provider options and evaluate each for our needs",
            "Comprehensive analysis of regulatory changes affecting our business",
            "Compare different pricing models and recommend best approach",
            "Root cause analysis of recent system outages",
        ],
        query_indicators=[
            # Research verbs
            "research",
            "investigate",
            "explore",
            "study",
            "examine",
            "analyze comprehensively",
            "deep dive into",
            # Strategic questions
            "what should we",
            "how should we",
            "recommend",
            "suggest",
            "strategy",
            "approach",
            "plan",
            # Evaluation
            "evaluate",
            "compare",
            "assess",
            "review",
            "options",
            "alternatives",
            "choices",
            # Investigation
            "why did",
            "what caused",
            "root cause",
            "reason for",
            "comprehensive",
            "thorough",
            "detailed analysis",
        ],
        not_suitable_for=[
            "simple factual questions",
            "single-source lookups",
            "straightforward database queries",
            "quick how-to questions",
        ],
        entry_state_type=ResearchState,
        executor="deep_research",
        fallback_chain=["rag_search", "web_search"],
        requires_confirmation=True,
    )
)

SubgraphRegistry.register(
    SubgraphConfig(
        name="direct_response",
        description=(
            "Provides direct conversational response without information retrieval. "
            "Handles social interaction, trivial common knowledge, follow-ups, "
            "and cases where no specialized subgraph is needed."
        ),
        when_to_use=(
            "Use when query is:\n"
            "• Social/conversational: greetings, thanks, farewells, small talk\n"
            "• Trivial common knowledge: universal facts, basic arithmetic, well-known information\n"
            "• Follow-up/clarification: asking to repeat, rephrase, or explain previous response\n"
            "• Vague/unclear: too ambiguous to route meaningfully\n"
            "• Meta-questions: about the assistant's capabilities or identity\n"
            "• Out of scope: nonsensical, gibberish, or completely unrelated\n"
            "• Fallback: when other subgraphs have failed and no retrieval path remains"
        ),
        examples=[
            "Hello! How are you?",
            "Thanks for your help!",
            "Good morning",
            "Goodbye, see you later",
            "What is 2 + 2?",
            "Capital of France?",
            "Speed of light?",
            "Can you repeat that?",
            "Explain what you just said",
            "Tell me more about that",
            "Rephrase in simpler terms",
            "More details please",
            "What do you mean?",
            "huh?",
            "???",
            "What can you do?",
            "Who created you?",
            "How does this work?",
        ],
        query_indicators=[
            # Social
            "hello",
            "hi",
            "hey",
            "good morning",
            "good afternoon",
            "thanks",
            "thank you",
            "appreciate",
            "grateful",
            "bye",
            "goodbye",
            "see you",
            "later",
            "how are you",
            "what's up",
            # Follow-ups
            "repeat",
            "again",
            "one more time",
            "rephrase",
            "reword",
            "say differently",
            "explain",
            "clarify",
            "what do you mean",
            "more detail",
            "elaborate",
            "expand",
            # Meta
            "what can you",
            "who are you",
            "who made you",
            "what are you",
            "how do you work",
            # Acknowledgments
            "okay",
            "ok",
            "got it",
            "I see",
            "understood",
        ],
        not_suitable_for=[
            "questions requiring information lookup or retrieval",
            "queries about specific entities, data, or documentation",
            "anything that could be answered by another subgraph",
        ],
        entry_state_type=None,
        executor=None,
        fallback_chain=None,
        requires_confirmation=False,
    )
)
