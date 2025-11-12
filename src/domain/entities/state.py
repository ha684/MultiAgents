# src/agents/graph/state.py
from typing import Any, Dict, List, Literal, Optional, Set, TypedDict

from langchain_core.documents import Document
from langchain_core.messages import BaseMessage


class SearchQuery(TypedDict):
    """Search query from search operations"""

    query: str
    priority: int
    search_type: Literal["rag", "web"]


class VerificationResult(TypedDict):
    """Verification result from verification operations"""

    sufficient: bool
    confidence: float
    missing_aspects: List[str]


class SearchResult(TypedDict):
    """Search result from search operations"""

    query: str
    documents: List[Document]
    search_type: Literal["rag", "web"]


class RetrievalContext(TypedDict):
    """Context from retrieval operations"""

    original_query: str
    contextualized_query: str
    total_retrieved: int
    total_cited: int
    cited_chunks: List[Document]
    search_method: Literal["rag", "web"]


class ExecutionRecord(TypedDict):
    """Record of a subgraph execution attempt"""

    subgraph: str
    error: Optional[str]
    timestamp: str
    result_summary: Optional[str]


class ReflectionResult(TypedDict):
    """Result from reflection agent"""

    is_sufficient: bool
    missing_aspects: List[str]
    reasoning: str
    suggested_next_action: str  # "search_more" | "switch_strategy" | "respond"
    refined_query: Optional[str]
    subgraphs_to_retry: List[str]


class SearchIteration(TypedDict):
    """Record of a single search iteration"""

    iteration: int
    subgraph: str
    query: str
    result_summary: str
    documents_count: int
    timestamp: str
    success: bool  # Whether this subgraph returned useful results
    error: Optional[str]  # Error message if subgraph failed


class OrchestratorState(TypedDict):
    """Enhanced state for agentic orchestrator"""

    conversation: List[BaseMessage]
    contextualized_query: Optional[str]

    route_decisions: Optional[List[str]]
    response_mode: Optional[str]
    execution_history: List[ExecutionRecord]

    subgraph_result: Optional[str]
    subgraph_error: Optional[str]

    main_context: Optional[str]
    cited_documents: Optional[List[Document]]

    subgraph_policy: Dict[str, Any]
    active_subgraphs: List[str]

    final_answer: Optional[str]
    response_metadata: Optional[Dict[str, Any]]

    search_iterations: List[SearchIteration]
    current_iteration: int
    accumulated_context: str

    subgraph_results: Dict[str, Dict[str, Any]]
    failed_subgraphs: Set[str]
    empty_result_subgraphs: Set[str]

    seen_urls: Set[str]
    seen_doc_ids: Set[str]
    duplicate_skip_ratio: float


class SimpleSearchState(TypedDict):
    """State for simple search operations"""

    conversation: List[BaseMessage]
    contextualized_query: str
    cited_documents: List[Document]
    response_metadata: Dict[str, Any]

    seen_urls: Set[str]
    seen_doc_ids: Set[str]
    duplicate_skip_ratio: float
    early_terminate: bool


class ResearchState(TypedDict, total=False):
    """State for research operations (simplified for efficiency)"""

    contextualized_query: str
    context_metadata: Dict[str, Any]

    breadth: int
    current_depth_level: int
    current_direction: str
    thinking_notes: str
    accumulated_knowledge: str
    learnings: List[str]
    search_count: int
    search_history: List[Dict[str, Any]]

    citation_counter: int
    cited_documents: List[Document]
    citation_map: List[Dict[str, Any]]

    used_rag_ids: List[str]
    used_web_urls: List[str]

    rag_available: bool
    web_available: bool

    _temp_documents: List[Document]
    _should_continue: bool
    _evaluation_result: Dict[str, Any]


class SqlState(TypedDict):
    """State for SQL query operations"""

    contextualized_query: str

    is_relevant: Optional[bool]
    irrelevance_reason: Optional[str]
    suggested_rephrase: Optional[str]

    analysis: Optional[Dict]

    generated_queries: Optional[List[Dict]]
    query_results: Optional[List[Dict]]
    chart_spec: Optional[Dict]

    response_metadata: Dict
