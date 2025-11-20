# src/agents/graph/state.py
from typing import Any, TypedDict

from langchain_core.documents import Document
from langchain_core.messages import BaseMessage

from src.domain.entities.graph import ResponseMode


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

    ChatGPT-style two-phase approach:
    1. Phase Agent: Decides phase_title and next_action
    2. Action Execution: Either generates reasoning OR selects tool+query
    """

    conversation: list[BaseMessage]
    final_answer: str
    response_metadata: dict[str, Any]

    iteration_count: int

    # Phase planning (from phase_agent)
    phase_title: str
    next_action: str  # "reason_only" or "use_tool"

    # Action execution results
    direction: str  # query for tool (when next_action="use_tool")
    selected_subgraph: str  # tool name (when next_action="use_tool")
    action: str  # legacy field, maps to next_action
    reasoning: str  # reasoning content (when next_action="reason_only")

    accumulated_context: str
    learnings: list[str]

    citation_counter: int
    cited_documents: list[Document]
    citation_map: list[dict[str, Any]]

    seen_content_hashes: list[str]

    response_mode: str
    has_tool_results: bool
    execution_history: list[dict[str, Any]]
    consecutive_failures: int
    _temp_documents: list[Document]
    _sql_result: str
    _is_sql_iteration: bool
    _should_continue: bool
    _missing_aspects: str
    internal_reasoning: str
    _execution_failed: bool
    _failure_reason: str


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
