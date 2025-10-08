# src/agents/graph/state.py
from typing import List, TypedDict, Dict, Optional, Literal, Any
from langchain_core.messages import BaseMessage
from langchain_core.documents import Document


class SearchQuery(TypedDict):
    """Search query from search operations"""

    query: str
    priority: int
    search_type: Literal["rag", "web"]


class SearchPlan(TypedDict):
    """Search plan from search operations"""

    core_queries: List[SearchQuery]
    optional_queries: List[SearchQuery]
    max_searches: int


class VerificationResult(TypedDict):
    """Verification result from verification operations"""

    sufficient: bool
    confidence: float
    next_action: Literal["continue_planned", "generate_dynamic", "synthesize"]
    missing_aspects: List[str]
    reasoning: str


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


class OrchestratorState(TypedDict):
    """State for orchestrator operations"""

    # Input & Core State
    conversation: List[BaseMessage]
    original_query: str
    contextualized_query: str
    route_decision: Optional[str]

    # --- Data from Simple Search Subgraph ---
    retrieval_contexts: RetrievalContext

    # --- Data from Research Subgraph ---
    accumulated_knowledge: str
    all_search_history: List[SearchResult]

    # Final Output
    final_answer: str
    response_metadata: Dict[str, Any]


class SimpleSearchState(TypedDict):
    """State for simple search operations"""

    conversation: List[BaseMessage]
    original_query: str
    contextualized_query: str

    retrieval_contexts: RetrievalContext
    response_metadata: Dict[str, Any]


class ResearchState(TypedDict):
    """State for research operations"""

    contextualized_query: str
    context_metadata: Dict[str, Any]
    search_plan: Optional[SearchPlan]
    pending_queries: List[SearchQuery]
    completed_queries: List[SearchQuery]
    accumulated_knowledge: str
    search_results: SearchResult
    all_search_history: List[SearchResult]
    iteration_count: int
    max_searches: int
    used_rag_ids: List[str]
    used_web_urls: List[str]
    should_switch_search_type: bool
    verification_result: Optional[VerificationResult]
    has_tried_rag: bool
    has_tried_web: bool
