# src/agents/graph/state.py
from typing import Any, Literal, TypedDict

from langchain_core.documents import Document
from langchain_core.messages import BaseMessage

from src.domain.entities.graph import ResponseMode


class SearchQuery(TypedDict):
    """Search query from search operations"""

    query: str
    priority: int
    search_type: Literal["rag", "web"]


class VerificationResult(TypedDict):
    """Verification result from verification operations"""

    sufficient: bool
    confidence: float
    missing_aspects: list[str]


class SearchResult(TypedDict):
    """Search result from search operations"""

    query: str
    documents: list[Document]
    search_type: Literal["rag", "web"]


class RetrievalContext(TypedDict):
    """Context from retrieval operations"""

    original_query: str
    contextualized_query: str
    total_retrieved: int
    total_cited: int
    cited_chunks: list[Document]
    search_method: Literal["rag", "web"]


class ExecutionRecord(TypedDict):
    """Record of a subgraph execution attempt"""

    subgraph: str
    error: str | None
    timestamp: str
    result_summary: str | None


class ReflectionResult(TypedDict):
    """Result from reflection agent"""

    is_sufficient: bool
    missing_aspects: list[str]
    reasoning: str
    suggested_next_action: str  # "search_more" | "switch_strategy" | "respond"
    refined_query: str | None
    subgraphs_to_retry: list[str]


class SearchIteration(TypedDict):
    """Record of a single search iteration"""

    iteration: int
    subgraph: str
    query: str
    result_summary: str
    documents_count: int
    timestamp: str
    success: bool  # Whether this subgraph returned useful results
    error: str | None  # Error message if subgraph failed


class MainGraphState(TypedDict):
    """Enhanced state for agentic orchestrator"""

    conversation: list[BaseMessage]
    main_context: str | None
    cited_documents: list[Document] | None

    final_answer: str | None
    response_metadata: dict[str, Any] | None

    accumulated_context: str
    route_mode: str


class SimpleSearchState(TypedDict):
    """State for simple search operations"""

    conversation: list[BaseMessage]
    direction: str
    cited_documents: list[Document]
    response_metadata: dict[str, Any]

    seen_urls: set[str]
    seen_doc_ids: set[str]
    duplicate_skip_ratio: float
    early_terminate: bool


class ThinkingState(TypedDict, total=False):
    """
    State for iterative research with reflection.
    Organized by purpose for clarity.
    """

    # ===== Core Input/Output =====
    conversation: list[BaseMessage]  # User conversation history
    final_answer: str  # Final synthesized response
    response_metadata: dict[str, Any]  # Metadata for response

    # ===== Current Iteration Context =====
    iteration_count: int  # Current iteration number (0-indexed)
    direction: str  # Current research direction/query
    selected_subgraph: str  # Subgraph to execute (e.g., "web_search")
    action: str  # "use_tool" or "reason_only"
    reasoning: str  # Reasoning from reflection_agent

    # ===== Accumulated Research =====
    accumulated_context: str  # Compressed knowledge from all iterations
    learnings: list[str]  # SIMPLIFIED: Human-readable log of learnings

    # ===== Citation Management =====
    citation_counter: int  # Next citation number to use
    cited_documents: list[Document]  # All documents cited so far
    citation_map: list[dict[str, Any]]  # Map of citation index -> metadata

    # ===== Deduplication Tracking =====
    seen_content_hashes: list[str]

    # ===== Response Mode =====
    response_mode: str  # ResponseMode enum value

    # ===== Flags for Path Tracking =====
    has_tool_results: bool  # Track if we've executed ANY tools (not just reasoning)
    execution_history: list[dict[str, Any]] = []  # Track all attempts
    consecutive_failures: int = 0
    # ===== Internal Control (private, prefixed with _) =====
    _temp_documents: list[Document]  # Temporary docs from current iteration
    _sql_result: str  # Temporary SQL result from current iteration
    _is_sql_iteration: bool  # Flag to indicate SQL iteration
    _should_continue: bool  # Should continue iterating?
    _missing_aspects: str  # What's missing (from evaluation)
    internal_reasoning: str  # Internal reasoning from current iteration


class SqlState(TypedDict):
    """State for SQL query operations"""

    conversation: list[BaseMessage]

    is_relevant: bool | None
    irrelevance_reason: str | None
    suggested_rephrase: str | None

    analysis: dict | None

    generated_queries: list[dict] | None
    query_results: list[dict] | None
    chart_spec: dict | None

    response_metadata: dict


class NormalGraphState(TypedDict):
    """State for normal graph operations"""

    final_answer: str
    response_metadata: dict
    conversation: list[BaseMessage]
    selected_subgraph: str
    direction: str
    cited_documents: list[Document]
    response_mode: ResponseMode
    accumulated_context: str
