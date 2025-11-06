# src/core/config/graph_configs.py
from src.domain.entities.graph import GraphMetadata, NodeMetadata
from src.domain.schemas.stream import StreamPhase

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
            # "extract_filename": NodeMetadata(
            #     display_message="Identifying sources...",
            #     stream_phase=StreamPhase.RETRIEVAL,
            #     show_in_ui=False,
            # ),
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
