from typing import Optional
from src.models.streaming import StreamPhase
from src.config.graph_configs import GRAPH_CONFIGS
from src.common.streaming import StreamEventBuilder


class AgenticStreamHandler:
    """Handles streaming events from graph execution"""

    def __init__(self):
        self.current_graph: Optional[str] = None
        self.graph_stack: list[str] = []
        self.last_phase: Optional[StreamPhase] = None
        self.last_emitted_message: Optional[str] = None
        self.content_index: int = 0
        self.last_phase = None

    async def handle_event(self, event: dict) -> Optional[str]:
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

    async def _handle_chain_start(self, name: str, event: dict) -> Optional[str]:
        """Handle chain/node start"""
        if name in GRAPH_CONFIGS:
            self.graph_stack.append(name)
            self.current_graph = name
            return None

        if self.current_graph:
            config = GRAPH_CONFIGS.get(self.current_graph)
            if config:
                node_meta = config.get_node_meta(name)
                if node_meta and node_meta.show_in_ui:
                    phase_changed = node_meta.stream_phase != self.last_phase
                    message_changed = (
                        node_meta.display_message != self.last_emitted_message
                    )

                    if phase_changed or message_changed:
                        self.last_phase = node_meta.stream_phase
                        self.last_emitted_message = node_meta.display_message

                        return StreamEventBuilder.status_update(
                            phase=node_meta.stream_phase,
                            message=node_meta.display_message,
                        )
        return None

    async def _handle_chain_end(self, name: str, event: dict) -> Optional[str]:
        """Handle chain/node end"""
        self.last_phase = None

        if name in GRAPH_CONFIGS:
            if self.graph_stack:
                self.graph_stack.pop()
            self.current_graph = self.graph_stack[-1] if self.graph_stack else None
            return None

        output = event.get("data", {}).get("output", {})

        if self.current_graph:
            config = GRAPH_CONFIGS.get(self.current_graph)
            if config:
                node_meta = config.get_node_meta(name)
                if node_meta and node_meta.emit_on_complete:
                    return await self._emit_completion_status(output)

        return await self._emit_rich_feedback(output)

    async def _emit_completion_status(self, output: dict) -> Optional[str]:
        """Emit status based on node completion"""

        if "retrieval_contexts" in output:
            retrieval = output["retrieval_contexts"]
            total_cited = retrieval.get("total_cited", 0)
            total_retrieved = retrieval.get("total_retrieved", 0)
            cited_chunks = retrieval.get("cited_chunks", [])
            if total_cited > 0 and retrieval.get("search_method") == "web":
                urls = []
                favicons = []
                for chunk in cited_chunks:
                    url = chunk.metadata.get("original_filename", "")
                    if url:
                        urls.append(url)
                    favicon = chunk.metadata.get("favicon", "")
                    if favicon:
                        favicons.append(favicon)
                return StreamEventBuilder.status_update(
                    phase=StreamPhase.RETRIEVAL,
                    message=f"Found {total_cited} relevant sources",
                    metadata={
                        "sources_count": total_cited,
                        "urls": urls,
                        "favicons": favicons,
                    },
                )
            elif total_retrieved > 0:
                return StreamEventBuilder.status_update(
                    phase=StreamPhase.RETRIEVAL,
                    message=f"Retrieved total {total_retrieved} documents",
                    metadata={"sources_count": total_retrieved},
                )
            else:
                return StreamEventBuilder.status_update(
                    phase=StreamPhase.RETRIEVAL,
                    message="No documents found",
                )

        return None

    async def _emit_rich_feedback(self, output: dict) -> Optional[str]:
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

    async def _handle_llm_stream(self, name: str, event: dict) -> Optional[str]:
        """Handle LLM streaming"""
        chunk = event["data"]["chunk"]

        if self.current_graph:
            config = GRAPH_CONFIGS.get(self.current_graph)
            if config:
                node_meta = config.get_node_meta(name)
                if node_meta and node_meta.stream_phase == StreamPhase.SYNTHESIS:
                    self.last_phase = StreamPhase.SYNTHESIS

        if self.last_phase == StreamPhase.SYNTHESIS:
            if chunk.content:
                sse_event = StreamEventBuilder.content_delta(
                    chunk.content, index=self.content_index
                )
                self.content_index += 1
                return sse_event

        else:
            if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                for tc in chunk.tool_call_chunks:
                    tool_name = tc.get("name")
                    if tool_name == "think":
                        args = tc.get("args", "")
                        if args:
                            return StreamEventBuilder.status_update(
                                phase=StreamPhase.ANALYSIS,
                                message=args,
                            )
            elif chunk.content:
                return StreamEventBuilder.status_update(
                    phase=StreamPhase.ANALYSIS,
                    message=chunk.content,
                )

        return None
