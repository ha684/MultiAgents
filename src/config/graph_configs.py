from dataclasses import dataclass
from typing import Dict, Optional
from enum import Enum
from src.models.streaming import StreamPhase


class GraphPhaseCategory(str, Enum):
    """High-level phase categories for grouping similar operations"""

    PLANNING = "planning"
    RETRIEVAL = "retrieval"
    PROCESSING = "processing"
    SYNTHESIS = "synthesis"


@dataclass
class NodeMetadata:
    """Metadata for a single node"""

    category: GraphPhaseCategory
    display_message: str
    stream_phase: StreamPhase
    show_in_ui: bool = True
    emit_on_complete: bool = False


@dataclass
class GraphMetadata:
    """Configuration for a graph"""

    name: str
    nodes: Dict[str, NodeMetadata]
    default_message: str = "Processing..."

    def get_node_meta(self, node_name: str) -> Optional[NodeMetadata]:
        """Get metadata for a node"""
        return self.nodes.get(node_name)


GRAPH_CONFIGS = {
    "MainOrchestrator": GraphMetadata(
        name="MainOrchestrator",
        nodes={
            "contextualize_query": NodeMetadata(
                category=GraphPhaseCategory.PLANNING,
                display_message="Understanding your question...",
                stream_phase=StreamPhase.PROCESSING,
            ),
            "router": NodeMetadata(
                category=GraphPhaseCategory.PLANNING,
                display_message="Planning approach...",
                stream_phase=StreamPhase.PROCESSING,
            ),
            "simple_search_subgraph": NodeMetadata(
                category=GraphPhaseCategory.RETRIEVAL,
                display_message="Searching for information...",
                stream_phase=StreamPhase.RETRIEVAL,
                show_in_ui=False,
            ),
            "research_subgraph_node": NodeMetadata(
                category=GraphPhaseCategory.RETRIEVAL,
                display_message="Conducting research...",
                stream_phase=StreamPhase.RETRIEVAL,
                show_in_ui=False,
            ),
            "final_synthesizer": NodeMetadata(
                category=GraphPhaseCategory.SYNTHESIS,
                display_message="Generating response...",
                stream_phase=StreamPhase.SYNTHESIS,
            ),
        },
    ),
    "SimpleSearchGraph": GraphMetadata(
        name="SimpleSearchGraph",
        nodes={
            "extract_filename": NodeMetadata(
                category=GraphPhaseCategory.PLANNING,
                display_message="Identifying sources...",
                stream_phase=StreamPhase.RETRIEVAL,
                show_in_ui=False,  # Internal step
            ),
            "retrieve_documents": NodeMetadata(
                category=GraphPhaseCategory.RETRIEVAL,
                display_message="Searching knowledge base...",
                stream_phase=StreamPhase.RETRIEVAL,
                emit_on_complete=True,  # Show results when done
            ),
            "filter_citations": NodeMetadata(
                category=GraphPhaseCategory.PROCESSING,
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
                category=GraphPhaseCategory.PLANNING,
                display_message="Planning research strategy...",
                stream_phase=StreamPhase.PROCESSING,
            ),
            "pre_flight_rag_check": NodeMetadata(
                category=GraphPhaseCategory.RETRIEVAL,
                display_message="Checking knowledge base...",
                stream_phase=StreamPhase.RETRIEVAL,
            ),
            "search_executor": NodeMetadata(
                category=GraphPhaseCategory.RETRIEVAL,
                display_message="Gathering information...",
                stream_phase=StreamPhase.RETRIEVAL,
                emit_on_complete=True,
            ),
            "process_results": NodeMetadata(
                category=GraphPhaseCategory.PROCESSING,
                display_message="Processing findings...",
                stream_phase=StreamPhase.PROCESSING,
                show_in_ui=False,  # Too fast
            ),
            "verification_agent": NodeMetadata(
                category=GraphPhaseCategory.PROCESSING,
                display_message="Verifying information...",
                stream_phase=StreamPhase.PROCESSING,
            ),
            "dynamic_query_generator": NodeMetadata(
                category=GraphPhaseCategory.PLANNING,
                display_message="Generating follow-up queries...",
                stream_phase=StreamPhase.RETRIEVAL,
            ),
            "handle_no_plan": NodeMetadata(
                category=GraphPhaseCategory.PLANNING,
                display_message="Adjusting strategy...",
                stream_phase=StreamPhase.PROCESSING,
                show_in_ui=False,
            ),
            "reflection_node": NodeMetadata(
                category=GraphPhaseCategory.PROCESSING,
                display_message="Reflecting on findings...",
                stream_phase=StreamPhase.PROCESSING,
            ),
        },
    ),
}
