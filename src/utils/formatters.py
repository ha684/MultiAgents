# src/utils/formatters.py
import json
from typing import Any

from src.core.config.graph_configs import GRAPH_CONFIGS
from src.domain.schemas.stream import StreamEvent, StreamEventType, StreamPhase
from src.utils.logger_conf import logger


class StreamEventBuilder:
    """Builder for creating standardized stream events"""

    @staticmethod
    def create_sse_event(
        event_type: StreamEventType | str,
        data: dict[str, Any],
        event_id: str | None = None,
    ) -> str:
        """Create SSE formatted event"""
        if isinstance(event_type, StreamEventType):
            event_type = event_type.value

        event = StreamEvent(type=event_type, data=data, id=event_id)

        sse_data = json.dumps(
            {
                **event.data,
                "id": event.id,
                "timestamp": event.timestamp,
            },
            ensure_ascii=False,
        )

        return f"event: {event.type}\ndata: {sse_data}\n\n"

    @staticmethod
    def message_start() -> str:
        """Start of message generation"""
        return StreamEventBuilder.create_sse_event(
            StreamEventType.MESSAGE_START, {"message": "Message generation started"}
        )

    @staticmethod
    def content_delta(text: str, index: int = 0) -> str:
        """Content chunk delta"""
        return StreamEventBuilder.create_sse_event(
            StreamEventType.MESSAGE_DELTA,
            {"delta": {"type": "text_delta", "text": text}, "index": index},
        )

    @staticmethod
    def thinking_delta(text: str, index: int = 0) -> str:
        """Thinking chunk delta"""
        return StreamEventBuilder.create_sse_event(
            StreamEventType.MESSAGE_DELTA,
            {"delta": {"type": "thinking_delta", "text": text}, "index": index},
        )

    @staticmethod
    def status_update(
        phase: StreamPhase | str,
        message: str,
        progress: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Status update"""
        if isinstance(phase, StreamPhase):
            phase = phase.value

        data = {
            "phase": phase,
            "message": message,
        }

        if progress is not None:
            data["progress"] = min(max(progress, 0.0), 1.0)

        if metadata:
            data["metadata"] = metadata

        return StreamEventBuilder.create_sse_event(StreamEventType.STATUS, data)

    @staticmethod
    def message_stop(
        final_message: str | dict[str, Any] | None = None,
        references: list | None = None,
        metadata: dict | None = None,
    ) -> str:
        """End of message"""
        data = {}

        if final_message:
            data["final_message"] = final_message

        if references:
            data["references"] = references

        if metadata:
            data["metadata"] = metadata

        return StreamEventBuilder.create_sse_event(StreamEventType.MESSAGE_STOP, data)

    @staticmethod
    def error(error_type: str, message: str, code: int | None = None) -> str:
        """Error event"""
        data = {"type": error_type, "message": message}

        if code:
            data["code"] = code

        return StreamEventBuilder.create_sse_event(StreamEventType.ERROR, data)


class AgenticStreamHandler:
    """Handles streaming events from graph execution

    Design principle: GRAPH_CONFIGS is the single source of truth.
    No need to maintain separate node lists.
    """

    def __init__(self):
        self.current_graph: str | None = None
        self.current_node: str | None = None
        self.graph_stack: list[str] = []
        self.last_phase: StreamPhase | None = None
        self.last_emitted_message: str | None = None
        self.content_index: int = 0
        self.thinking_index: int = 0

    async def handle_event(self, event: dict) -> str | None:
        """Process a single event and return SSE event if needed"""
        kind = event["event"]
        name = event.get("name", "")

        if kind == "on_chain_start":
            return await self._handle_chain_start(name, event)

        elif kind == "on_chain_end":
            return await self._handle_chain_end(name, event)

        elif kind == "on_chat_model_stream":
            return await self._handle_llm_stream(name, event)

        return None

    async def _handle_chain_start(self, name: str, event: dict) -> str | None:
        """Handle chain/node start

        Key insight: name here is the node name (e.g., "final_synthesizer")
        """
        if name in GRAPH_CONFIGS:
            self.graph_stack.append(name)
            self.current_graph = name
            return None

        if self.current_graph:
            config = GRAPH_CONFIGS.get(self.current_graph)
            if config:
                node_meta = config.get_node_meta(name)

                if node_meta:
                    self.current_node = name
                    self.last_phase = node_meta.stream_phase
                    if node_meta.show_in_ui:
                        message_changed = (
                            node_meta.display_message != self.last_emitted_message
                        )

                        if message_changed:
                            self.last_emitted_message = node_meta.display_message
                            return StreamEventBuilder.status_update(
                                phase=node_meta.stream_phase,
                                message=node_meta.display_message,
                            )
                    return None

        for graph_name, config in GRAPH_CONFIGS.items():
            node_meta = config.get_node_meta(name)
            if node_meta:
                self.current_graph = graph_name
                self.current_node = name
                self.last_phase = node_meta.stream_phase

                self.graph_stack = [graph_name]

                if node_meta.show_in_ui:
                    self.last_emitted_message = node_meta.display_message
                    return StreamEventBuilder.status_update(
                        phase=node_meta.stream_phase,
                        message=node_meta.display_message,
                    )
                return None

        return None

    async def _handle_chain_end(self, name: str, event: dict) -> str | None:
        """Handle chain/node end"""
        if name in GRAPH_CONFIGS:
            if self.graph_stack:
                self.graph_stack.pop()
            self.current_graph = self.graph_stack[-1] if self.graph_stack else None

            if not self.current_graph:
                self.current_node = None
                self.last_phase = None
            return None

        output = event.get("data", {}).get("output", {})

        if self.current_graph:
            config = GRAPH_CONFIGS.get(self.current_graph)
            if config:
                node_meta = config.get_node_meta(name)
                if node_meta and node_meta.emit_on_complete:
                    return await self._emit_completion_status(output)

        return await self._emit_rich_feedback(output)

    async def _emit_completion_status(self, output: dict) -> str | None:
        """Emit status based on node completion"""

        def extract_urls_and_favicons(items):
            """Extract URLs and favicons from chunks or documents"""
            urls = []
            favicons = []
            for item in items:
                # Handle both Document objects and dicts
                metadata = (
                    item.metadata
                    if hasattr(item, "metadata")
                    else item.get("metadata", {})
                )

                # Try multiple common keys for URL
                url = (
                    metadata.get("source")
                    or metadata.get("url")
                    or metadata.get("original_filename")
                    or ""
                )
                if url:
                    urls.append(url)

                if favicon := metadata.get("favicon", ""):
                    favicons.append(favicon)
            return urls, favicons

        # Handle ThinkingGraph SQL result
        if "_sql_result" in output:
            sql_result = output["_sql_result"]
            return StreamEventBuilder.status_update(
                phase=StreamPhase.RETRIEVAL,
                message="Executed SQL Query",
                metadata={"sql_result_preview": str(sql_result)[:200]},
            )

        # Handle Documents (ThinkingGraph: _temp_documents, NormalGraph: cited_documents)
        documents = output.get("cited_documents") or output.get("_temp_documents") or []

        if documents:
            count = len(documents)
            urls, favicons = extract_urls_and_favicons(documents)

            return StreamEventBuilder.status_update(
                phase=StreamPhase.RETRIEVAL,
                message=f"Found {count} relevant sources",
                metadata={
                    "sources_count": count,
                    "urls": urls,
                    "favicons": favicons,
                },
            )

        return None

    async def _emit_rich_feedback(self, output: dict) -> str | None:
        """Emit rich feedback for certain outputs"""

        if "all_search_history" in output:
            search_history = output["all_search_history"]
            if search_history:
                latest_query = search_history[-1].get("query", "")
                return StreamEventBuilder.status_update(
                    phase=StreamPhase.RETRIEVAL,
                    message=f"Searched: {latest_query}",
                    metadata={
                        "search_count": len(search_history),
                        "latest_query": latest_query,
                    },
                )

        if "cited_documents" in output:
            cited_docs = output["cited_documents"]
            if cited_docs:
                return StreamEventBuilder.status_update(
                    phase=StreamPhase.PROCESSING,
                    message=f"Selected {len(cited_docs)} sources",
                    metadata={"sources_count": len(cited_docs)},
                )

        return None

    async def _handle_llm_stream(self, name: str, event: dict) -> str | None:
        """Handle LLM streaming

        Key insight: name here is the model name (e.g., "ChatOpenAI"),
        NOT the node name. We must use self.current_node instead.
        """
        chunk = event["data"]["chunk"]

        if self.current_graph and self.current_node:
            config = GRAPH_CONFIGS.get(self.current_graph)
            if config:
                node_meta = config.get_node_meta(self.current_node)

                if not node_meta:
                    logger.warning(
                        f"Node '{self.current_node}' not found in graph '{self.current_graph}'. "
                        f"Possible orphaned state from terminated subgraph."
                    )
                    for graph_name, cfg in GRAPH_CONFIGS.items():
                        if cfg.get_node_meta(self.current_node):
                            logger.info(f"Correcting graph context to '{graph_name}'")
                            self.current_graph = graph_name
                            self.graph_stack = [graph_name]
                            config = cfg
                            node_meta = cfg.get_node_meta(self.current_node)
                            break

                if node_meta:
                    self.last_phase = node_meta.stream_phase

        if self.last_phase == StreamPhase.SYNTHESIS:
            if chunk.content:
                sse_event = StreamEventBuilder.content_delta(
                    chunk.content, index=self.content_index
                )
                self.content_index += 1
                return sse_event

        # Handle Analysis/Processing as thinking tokens
        elif self.last_phase in [StreamPhase.ANALYSIS, StreamPhase.PROCESSING]:
            # Handle tool calls as status updates if needed (keeping backward compat for thinking tools)
            if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                for tc in chunk.tool_call_chunks:
                    tool_name = tc.get("name")
                    if tool_name == "think":
                        args = tc.get("args", "")
                        if args:
                            # Stream thinking args as thinking delta too if preferred,
                            # or keep as status. But user asked for "tokens".
                            # Often "think" tool streams arguments.
                            evt = StreamEventBuilder.thinking_delta(
                                args, index=self.thinking_index
                            )
                            self.thinking_index += 1
                            return evt
                            # self.thinking_index += 1 (handled in next calls?)
                            # Actually if we return, we can't increment here easily unless we do it before return.
                            # But this is inside loop.
                            # Let's stick to tokens.

            if chunk.content:
                sse_event = StreamEventBuilder.thinking_delta(
                    chunk.content, index=self.thinking_index
                )
                self.thinking_index += 1
                return sse_event

        else:
            # Fallback for other phases if content appears
            if chunk.content:
                return StreamEventBuilder.status_update(
                    phase=self.last_phase or StreamPhase.ANALYSIS,
                    message=chunk.content,
                )

        return None
