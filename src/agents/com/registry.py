# src/agents/com/registry.py
from typing import Dict, List, Optional, Type
from dataclasses import dataclass
from src.agents.graph.state import SimpleSearchState, ResearchState, SqlState


@dataclass
class SubgraphConfig:
    """Configuration for registering a subgraph as a tool"""

    name: str
    description: str
    when_to_use: str
    examples: List[str]
    entry_state_type: Type
    executor: str
    fallback_chain: Optional[List[str]] = None
    requires_confirmation: bool = False

    # New: indicators for router
    query_indicators: Optional[List[str]] = None
    not_suitable_for: Optional[List[str]] = None


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
            tool_desc = f"{config.description}\n\n**When to use:** {config.when_to_use}"

            if config.examples:
                tool_desc += "\n\n**Examples:**\n" + "\n".join(
                    f"- {ex}" for ex in config.examples[:3]
                )

            if config.query_indicators:
                tool_desc += (
                    f"\n\n**Query indicators:** {', '.join(config.query_indicators)}"
                )

            if config.not_suitable_for:
                tool_desc += (
                    f"\n\n**Not suitable for:** {', '.join(config.not_suitable_for)}"
                )

            tools.append({"name": name, "description": tool_desc})

        return tools

    @classmethod
    def get_subgraph(cls, name: str) -> Optional[SubgraphConfig]:
        """Get subgraph config"""
        return cls._subgraphs.get(name)


SubgraphRegistry.register(
    SubgraphConfig(
        name="rag_search",
        description="Fast RAG-based search over internal knowledge base for straightforward questions",
        when_to_use="Query has clear information need answerable by internal documents in single retrieval pass",
        examples=[
            "What is the company's revenue policy?",
            "How do I reset my password?",
            "What are the office hours?",
            "Explain our product's key features",
        ],
        query_indicators=["policy", "how to", "what is", "documentation", "internal"],
        not_suitable_for=[
            "real-time data",
            "external news",
            "exploratory research",
            "database metrics",
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
        description="Targeted web search for up-to-date or external public information",
        when_to_use="Query needs external sources, real-time updates, public references, or when RAG coverage insufficient",
        examples=[
            "What are the latest changes to ISO 27001 in 2025?",
            "Recent news about competitor X's product launch",
            "Current industry benchmark for churn rate",
            "Latest AI developments in healthcare",
        ],
        query_indicators=[
            "latest",
            "recent",
            "news",
            "current",
            "competitor",
            "industry",
            "trend",
        ],
        not_suitable_for=[
            "internal policies",
            "company-specific data",
            "database queries",
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
        description="Multi-step iterative research requiring progressive exploration and synthesis",
        when_to_use="Query needs exploratory investigation where answer path unclear upfront, requires multiple search iterations with adaptive strategy",
        examples=[
            "Research emerging AI trends and their impact on our industry",
            "Investigate why sales dropped and recommend solutions",
            "What should our market strategy be for next year?",
            "Explore expansion options to Asia and evaluate each",
            "Build comprehensive analysis of regulatory landscape",
        ],
        query_indicators=[
            "research",
            "investigate",
            "explore",
            "analyze comprehensively",
            "what should we",
            "why did",
        ],
        not_suitable_for=[
            "simple facts",
            "single-document answers",
            "database queries",
            "greetings",
        ],
        entry_state_type=ResearchState,
        executor="deep_research",
        fallback_chain=["rag_search", "web_search"],
        requires_confirmation=True,
    )
)

SubgraphRegistry.register(
    SubgraphConfig(
        name="sql_query",
        description="Execute SQL queries on structured databases for precise metrics and data retrieval",
        when_to_use="Query explicitly requests structured data, metrics, counts, or aggregations from database tables",
        examples=[
            "How many users signed up last month?",
            "Show me sales by region",
            "What's the average order value?",
            "List top 10 customers by revenue",
            "Count failed transactions yesterday",
        ],
        query_indicators=[
            "how many",
            "count",
            "show data",
            "list",
            "total",
            "average",
            "sum",
            "by region/category",
        ],
        not_suitable_for=[
            "document search",
            "conceptual questions",
            "external data",
            "analysis requiring documents",
        ],
        entry_state_type=SqlState,
        executor="sql_query",
        fallback_chain=["rag_search", "web_search", "deep_research"],
        requires_confirmation=False,
    )
)

SubgraphRegistry.register(
    SubgraphConfig(
        name="direct_response",
        description="Direct conversational response without subgraph execution - for various non-retrieval scenarios",
        when_to_use=(
            "Use for queries that don't require information retrieval:\n"
            "1. **Social/Conversational**: Greetings, thanks, acknowledgments, small talk\n"
            "2. **Basic Knowledge**: Extremely straightforward facts, definitions, theorems that don't need retrieval\n"
            "3. **Follow-up/Clarification**: Asking to repeat, explain differently, or clarify previous response\n"
            "4. **Vague/Incomplete**: Query is too vague, incomplete, or unclear to route meaningfully\n"
            "5. **Out of Scope**: Nonsensical, gibberish, or completely unrelated to available capabilities\n"
            "6. **Meta-questions**: About the assistant itself, its capabilities, or how it works\n"
            "7. **Fallback**: After multiple failed retrieval attempts from other subgraphs"
        ),
        examples=[
            "Hello! How are you?",
            "Thanks for your help!",
            "What is 2+2?",
            "What's the capital of France?",
            "Can you explain that again?",
            "Repeat what you just said",
            "More details please",
            "huh?",
            "asdfghjkl",
            "What can you do?",
            "Who created you?",
            "[After rag_search, web_search both failed]",
        ],
        query_indicators=[
            "hello",
            "hi",
            "thanks",
            "thank you",
            "bye",
            "what is [basic fact]",
            "define",
            "repeat",
            "again",
            "explain that",
            "rephrase",
            "more detail",
            "huh",
            "what",
            "unclear",
            "?",
            "what can you",
            "who are you",
            "how do you work",
        ],
        not_suitable_for=[
            "specific information requests",
            "research needs",
            "data queries that can be retrieved",
        ],
        entry_state_type=None,
        executor=None,
        fallback_chain=None,
        requires_confirmation=False,
    )
)
