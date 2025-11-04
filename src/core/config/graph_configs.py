# src/core/config/graph_configs.py
from src.domain.entities.graph import GraphMetadata, NodeMetadata, SubgraphConfig
from src.domain.entities.state import ResearchState, SimpleSearchState
from src.domain.schemas.stream import StreamPhase

GRAPH_CONFIGS = {
    "MainOrchestrator": GraphMetadata(
        name="MainOrchestrator",
        nodes={
            "contextualize_query": NodeMetadata(
                display_message="Understanding your question...",
                stream_phase=StreamPhase.PROCESSING,
            ),
            "router": NodeMetadata(
                display_message="Planning approach...",
                stream_phase=StreamPhase.PROCESSING,
            ),
            "dispatch_subgraph": NodeMetadata(
                display_message="Processing request...",
                stream_phase=StreamPhase.PROCESSING,
                show_in_ui=False,
            ),
            "final_response": NodeMetadata(
                display_message="Generating response...",
                stream_phase=StreamPhase.SYNTHESIS,
            ),
        },
    ),
    "SimpleSearchGraph": GraphMetadata(
        name="SimpleSearchGraph",
        nodes={
            "extract_filename": NodeMetadata(
                display_message="Identifying sources...",
                stream_phase=StreamPhase.RETRIEVAL,
                show_in_ui=False,
            ),
            "retrieve_documents": NodeMetadata(
                display_message="Searching knowledge base...",
                stream_phase=StreamPhase.RETRIEVAL,
                emit_on_complete=True,
            ),
            "filter_citations": NodeMetadata(
                display_message="Selecting relevant information...",
                stream_phase=StreamPhase.PROCESSING,
                emit_on_complete=True,
            ),
        },
    ),
    "ResearchGraph": GraphMetadata(
        name="ResearchGraph",
        nodes={
            "query_planner": NodeMetadata(
                display_message="Planning research strategy...",
                stream_phase=StreamPhase.PROCESSING,
            ),
            "pre_flight_rag_check": NodeMetadata(
                display_message="Checking knowledge base...",
                stream_phase=StreamPhase.PROCESSING,
            ),
            "search_executor": NodeMetadata(
                display_message="Gathering information...",
                stream_phase=StreamPhase.RETRIEVAL,
                emit_on_complete=True,
            ),
            "process_results": NodeMetadata(
                display_message="Processing findings...",
                stream_phase=StreamPhase.PROCESSING,
            ),
            "verification_agent": NodeMetadata(
                display_message="Verifying information...",
                stream_phase=StreamPhase.PROCESSING,
            ),
            "dynamic_query_generator": NodeMetadata(
                display_message="Generating follow-up queries...",
                stream_phase=StreamPhase.RETRIEVAL,
            ),
            "handle_no_plan": NodeMetadata(
                display_message="Adjusting strategy...",
                stream_phase=StreamPhase.PROCESSING,
                show_in_ui=False,
            ),
            "reflection_node": NodeMetadata(
                display_message="Reflecting on findings...",
                stream_phase=StreamPhase.PROCESSING,
            ),
        },
    ),
    "SqlGraph": GraphMetadata(
        name="SqlGraph",
        nodes={
            "validate_relevance": NodeMetadata(
                display_message="Validating query relevance...",
                stream_phase=StreamPhase.PROCESSING,
            ),
            "analyze_query": NodeMetadata(
                display_message="Analyzing data requirements...",
                stream_phase=StreamPhase.PROCESSING,
            ),
            "generate_sql_queries": NodeMetadata(
                display_message="Generating SQL queries...",
                stream_phase=StreamPhase.PROCESSING,
            ),
            "validate_queries": NodeMetadata(
                display_message="Validating SQL syntax...",
                stream_phase=StreamPhase.PROCESSING,
            ),
            "execute_queries": NodeMetadata(
                display_message="Executing database queries...",
                stream_phase=StreamPhase.RETRIEVAL,
                emit_on_complete=True,
            ),
            "generate_chart": NodeMetadata(
                display_message="Generating visualization...",
                stream_phase=StreamPhase.PROCESSING,
                emit_on_complete=True,
            ),
        },
    ),
}

RAG_SEARCH_CONFIG = SubgraphConfig(
    name="rag_search",
    description=(
        "Searches internal knowledge base using semantic search. "
        "For company docs, policies, procedures, and product documentation."
    ),
    when_to_use=(
        "• Questions about internal/proprietary information\n"
        "• Company policies, procedures, or guidelines\n"
        "• Product features, capabilities, or documentation\n"
        "• How-to questions about internal systems/processes"
    ),
    examples=[
        "What is our refund policy?",
        "How do I submit a leave request?",
        "Explain our product's authentication flow",
        "What are the onboarding steps for new employees?",
    ],
    query_indicators=[
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
    ],
    not_suitable_for=[
        "external/public information",
        "current events or news",
        "structured data queries",
    ],
    entry_state_type=SimpleSearchState,
    executor="rag_search",
    fallback_chain=["web_search", "deep_research"],
)

WEB_SEARCH_CONFIG = SubgraphConfig(
    name="web_search",
    description=(
        "Searches public web for external information. "
        "For news, industry data, competitors, regulations, and public knowledge."
    ),
    when_to_use=(
        "• Current events, news, or recent developments\n"
        "• External entities (competitors, industry, market)\n"
        "• Public standards, regulations, or certifications\n"
        "• Time-sensitive information that may have changed"
    ),
    examples=[
        "Latest AI developments in 2025",
        "Competitor X's recent product launch",
        "Current GDPR requirements",
        "Industry benchmark for SaaS pricing",
    ],
    query_indicators=[
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
    ],
    not_suitable_for=[
        "internal company information",
        "database metrics",
        "proprietary data",
    ],
    entry_state_type=SimpleSearchState,
    executor="web_search",
    fallback_chain=["rag_search", "deep_research"],
)

DEEP_RESEARCH_CONFIG = SubgraphConfig(
    name="deep_research",
    description=(
        "Multi-step iterative research with reflection. "
        "Combines RAG + web search with adaptive strategy for complex analysis."
    ),
    when_to_use=(
        "• Complex questions requiring multiple information sources\n"
        "• Strategic analysis or recommendations\n"
        "• Comparative evaluation of multiple options\n"
        "• Root cause investigation or comprehensive analysis"
    ),
    examples=[
        "Analyze cloud providers and recommend the best for our needs",
        "Why did sales drop last quarter? Investigate and suggest solutions",
        "Research AI trends and their impact on our industry",
        "Compare pricing models and recommend an approach",
    ],
    query_indicators=[
        "research",
        "investigate",
        "analyze",
        "compare",
        "evaluate",
        "recommend",
        "strategy",
        "why did",
        "root cause",
        "comprehensive",
        "thorough",
    ],
    not_suitable_for=[
        "simple lookups",
        "single-fact questions",
        "straightforward queries",
    ],
    entry_state_type=ResearchState,
    executor="deep_research",
    fallback_chain=["rag_search", "web_search"],
)

DIRECT_RESPONSE_CONFIG = SubgraphConfig(
    name="direct_response",
    description=(
        "Direct conversational response without retrieval. "
        "For greetings, common knowledge, clarifications, and fallback."
    ),
    when_to_use=(
        "• Social: greetings, thanks, goodbyes\n"
        "• Trivial common knowledge: basic facts, simple math\n"
        "• Follow-ups: clarification, repetition, elaboration\n"
        "• Meta: questions about assistant capabilities\n"
        "• Fallback: when other subgraphs have failed"
    ),
    examples=[
        "Hello, how are you?",
        "Thanks!",
        "What is 2 + 2?",
        "Capital of France?",
        "Can you explain that again?",
        "What can you do?",
    ],
    query_indicators=[
        "hello",
        "hi",
        "thanks",
        "bye",
        "repeat",
        "clarify",
        "explain again",
        "what can you",
        "who are you",
    ],
    not_suitable_for=[
        "anything requiring information retrieval",
        "specific entity or data queries",
    ],
    entry_state_type=None,
    executor=None,
    fallback_chain=None,
)
