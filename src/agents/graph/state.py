# src/agents/graph/state.py
from typing import Any, Dict, List, Literal, Optional, TypedDict

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
    """Result from reflection/evaluation step"""

    is_sufficient: bool
    missing_aspects: List[str]
    reasoning: str
    suggested_next_action: Literal["search_more", "switch_strategy", "respond"]
    refined_query: Optional[str]


class SearchIteration(TypedDict):
    """Record of a single search iteration"""

    iteration: int
    subgraph: str
    query: str
    result_summary: str
    documents_count: int
    timestamp: str


class OrchestratorState(TypedDict):
    """Enhanced state for agentic orchestrator"""

    conversation: List[BaseMessage]
    contextualized_query: Optional[str]

    route_decision: Optional[str]
    response_mode: Optional[str]
    execution_history: List[ExecutionRecord]

    subgraph_result: Optional[str]
    subgraph_error: Optional[str]

    main_context: Optional[str]
    cited_documents: Optional[List[Document]]

    subgraph_policy: Dict[
        str, Any
    ]  # {allow: [..] | None, block: [..], extras: Dict[name, SubgraphConfig]}
    active_subgraphs: List[str]

    final_answer: Optional[str]
    response_metadata: Optional[Dict[str, Any]]

    # New fields for iterative reasoning
    search_iterations: List[SearchIteration]
    current_iteration: int
    max_iterations: int
    accumulated_context: str
    reflection_result: Optional[ReflectionResult]
    needs_confirmation: Optional[bool]


class SimpleSearchState(TypedDict):
    """State for simple search operations"""

    conversation: List[BaseMessage]
    contextualized_query: str
    cited_documents: List[Document]
    response_metadata: Dict[str, Any]


class ResearchState(TypedDict):
    """State for research operations"""

    contextualized_query: str
    context_metadata: Dict[str, Any]
    pending_queries: List[SearchQuery]
    completed_queries: List[SearchQuery]
    accumulated_knowledge: str
    search_results: SearchResult
    all_search_history: List[SearchResult]
    iteration_count: int
    max_searches: int
    used_rag_ids: List[str]
    used_web_urls: List[str]
    verification_result: Optional[VerificationResult]
    has_tried_rag: bool
    has_tried_web: bool
    consecutive_search_failures: int
    citation_counter: int
    cited_documents: List[Document]

    rag_is_unavailable: bool
    web_is_unavailable: bool

    should_retry_query: bool
    is_rag_source_relevant: bool


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
