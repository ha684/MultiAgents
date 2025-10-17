from dataclasses import dataclass
from typing import Dict, Optional
from src.models.streaming import StreamPhase


@dataclass
class NodeMetadata:
    """Metadata for a single node"""

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
                display_message="Understanding your question...",
                stream_phase=StreamPhase.PROCESSING,
            ),
            "router": NodeMetadata(
                display_message="Planning approach...",
                stream_phase=StreamPhase.PROCESSING,
            ),
            "simple_search_subgraph": NodeMetadata(
                display_message="Searching for information...",
                stream_phase=StreamPhase.RETRIEVAL,
                show_in_ui=False,
            ),
            "research_subgraph_node": NodeMetadata(
                display_message="Conducting research...",
                stream_phase=StreamPhase.RETRIEVAL,
                show_in_ui=False,
            ),
            "final_synthesizer": NodeMetadata(
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
                show_in_ui=False,  # Internal step
            ),
            "retrieve_documents": NodeMetadata(
                display_message="Searching knowledge base...",
                stream_phase=StreamPhase.RETRIEVAL,
                emit_on_complete=True,  # Show results when done
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
}
