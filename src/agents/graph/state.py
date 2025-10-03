# src/agents/graph/state.py
from typing import List, TypedDict, Dict, Optional, Literal, Any
from langchain_core.messages import BaseMessage
from langchain_core.documents import Document


class SearchQuery(TypedDict):
    query: str
    priority: int
    search_type: Literal["rag", "web"]


class SearchPlan(TypedDict):
    core_queries: List[SearchQuery]
    optional_queries: List[SearchQuery]
    max_searches: int


class VerificationResult(TypedDict):
    sufficient: bool
    confidence: float
    next_action: Literal["continue_planned", "generate_dynamic", "synthesize"]
    missing_aspects: List[str]
    reasoning: str


class SearchResult(TypedDict):
    query: str
    content: str
    source_ids: List[str]
    search_type: Literal["rag", "web"]
    timestamp: str


class RetrievalContext(TypedDict):
    """Context from retrieval operations"""

    original_query: str
    contextualized_query: str
    total_retrieved: int
    total_cited: int
    cited_chunks: List[Document]


# ==================== ORCHESTRATOR STATE ====================
class OrchestratorState(TypedDict):
    # Input & Core State
    conversation: List[BaseMessage]
    original_query: str
    contextualized_query: str
    route_decision: Optional[str]

    # Data passed between nodes
    accumulated_knowledge: str  # Output from ResearchGraph
    retrieval_contexts: List[RetrievalContext]  # Output from SimpleSearchGraph

    # Final Output
    final_answer: str
    response_metadata: Dict[str, Any]


class SimpleSearchState(TypedDict):
    conversation: List[BaseMessage]
    original_query: str
    contextualized_query: str

    retrieval_contexts: List[RetrievalContext]
    response_metadata: Dict[str, Any]


class ResearchState(TypedDict):
    contextualized_query: str
    search_plan: Optional[SearchPlan]
    pending_queries: List[SearchQuery]
    completed_queries: List[SearchQuery]
    accumulated_knowledge: str
    search_results: List[SearchResult]
    all_search_history: List[SearchResult]
    iteration_count: int
    max_searches: int
    used_rag_ids: List[str]
    used_web_urls: List[str]
    should_switch_search_type: bool
    verification_result: Optional[VerificationResult]
