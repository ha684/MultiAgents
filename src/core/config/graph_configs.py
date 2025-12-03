# src/core/config/graph_configs.py
from src.domain.entities.graph import GraphMetadata, NodeMetadata
from src.domain.schemas.stream import StreamPhase

GRAPH_CONFIGS = {
    "MainGraph": GraphMetadata(
        name="MainGraph",
        nodes={
            "direct_response": NodeMetadata(
                display_message="Processing your request...",
                stream_phase=StreamPhase.SYNTHESIS,
            ),
            "execute_normal": NodeMetadata(
                display_message="Executing fast path...",
                stream_phase=StreamPhase.PROCESSING,
            ),
            "execute_thinking": NodeMetadata(
                display_message="Executing research mode...",
                stream_phase=StreamPhase.PROCESSING,
            ),
        },
    ),
    "NormalGraph": GraphMetadata(
        name="NormalGraph",
        nodes={
            "generate_direction": NodeMetadata(
                display_message="Planning approach...",
                stream_phase=StreamPhase.PROCESSING,
            ),
            "execute_subgraph": NodeMetadata(
                display_message="Gathering information...",
                stream_phase=StreamPhase.RETRIEVAL,
                emit_on_complete=True,
            ),
            "synthesize_response": NodeMetadata(
                display_message="Generating response...",
                stream_phase=StreamPhase.SYNTHESIS,
            ),
        },
    ),
    "ThinkingGraph": GraphMetadata(
        name="ThinkingGraph",
        nodes={
            "generate_direction": NodeMetadata(
                display_message="Planning research step...",
                stream_phase=StreamPhase.PROCESSING,
            ),
            "execute_subgraph": NodeMetadata(
                display_message="Gathering information...",
                stream_phase=StreamPhase.RETRIEVAL,
                emit_on_complete=True,
            ),
            "pure_reasoning": NodeMetadata(
                display_message="Analyzing information...",
                stream_phase=StreamPhase.PROCESSING,
            ),
            "extract_learnings": NodeMetadata(
                display_message="Extracting insights...",
                stream_phase=StreamPhase.PROCESSING,
            ),
            "evaluate_sufficiency": NodeMetadata(
                display_message="Evaluating completeness...",
                stream_phase=StreamPhase.PROCESSING,
            ),
            "continue_iteration": NodeMetadata(
                display_message="Continuing research...",
                stream_phase=StreamPhase.PROCESSING,
            ),
            "synthesize_response": NodeMetadata(
                display_message="Generating response...",
                stream_phase=StreamPhase.SYNTHESIS,
            ),
        },
    ),
    "SimpleSearchGraph": GraphMetadata(
        name="SimpleSearchGraph",
        nodes={
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
