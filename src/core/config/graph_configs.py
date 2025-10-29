# src/core/config/graph_configs.py
from src.domain.entities.graph import GraphMetadata, NodeMetadata, SubgraphConfig
from src.domain.schemas.stream import StreamPhase
from src.agents.graph.state import SimpleSearchState, ResearchState

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

WEB_SEARCH_CONFIG = SubgraphConfig(
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

DEEP_RESEARCH_CONFIG = SubgraphConfig(
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

DIRECT_RESPONSE_CONFIG = SubgraphConfig(
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
