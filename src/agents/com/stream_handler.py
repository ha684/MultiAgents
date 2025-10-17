from typing import Optional
from src.models.streaming import StreamPhase
from src.config.graph_configs import GRAPH_CONFIGS
from src.common.streaming import StreamEventBuilder
from src.utils.logger_conf import logger


class AgenticStreamHandler:
    """Handles streaming events from graph execution

    Design principle: GRAPH_CONFIGS is the single source of truth.
    No need to maintain separate node lists.
    """

    def __init__(self):
        self.current_graph: Optional[str] = None
        self.current_node: Optional[str] = None
        self.graph_stack: list[str] = []
        self.last_phase: Optional[StreamPhase] = None
        self.last_emitted_message: Optional[str] = None
        self.content_index: int = 0

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

    async def _handle_chain_end(self, name: str, event: dict) -> Optional[str]:
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

    async def _emit_completion_status(self, output: dict) -> Optional[str]:
        """Emit status based on node completion"""

        def extract_urls_and_favicons(items):
            """Extract URLs and favicons from chunks or documents"""
            urls = []
            favicons = []
            for item in items:
                if url := item.metadata.get("original_filename", ""):
                    urls.append(url)
                if favicon := item.metadata.get("favicon", ""):
                    favicons.append(favicon)
            return urls, favicons

        def build_retrieval_status(message, sources_count, urls=None, favicons=None):
            """Build retrieval status with optional web metadata"""
            metadata = {"sources_count": sources_count}
            if urls and favicons:
                metadata.update({"urls": urls, "favicons": favicons})
            return StreamEventBuilder.status_update(
                phase=StreamPhase.RETRIEVAL,
                message=message,
                metadata=metadata,
            )

        if "retrieval_contexts" in output:
            retrieval = output["retrieval_contexts"]
            total_cited = retrieval.get("total_cited", 0)
            total_retrieved = retrieval.get("total_retrieved", 0)

            if total_cited > 0 and retrieval.get("search_method") == "web":
                urls, favicons = extract_urls_and_favicons(
                    retrieval.get("cited_chunks", [])
                )
                return build_retrieval_status(
                    f"Found {total_cited} relevant sources",
                    total_cited,
                    urls,
                    favicons,
                )
            elif total_retrieved > 0:
                return build_retrieval_status(
                    f"Retrieved total {total_retrieved} documents",
                    total_retrieved,
                )
            else:
                return build_retrieval_status("No documents found", 0)

        if "search_results" in output:
            search_results = output["search_results"]
            documents = search_results.get("documents", [])
            search_type = search_results.get("search_type", "")
            doc_count = len(documents)

            if doc_count == 0:
                return build_retrieval_status("No documents found", 0)

            message = f"Searched: {search_results.get('query', '')}"

            if search_type == "web":
                urls, favicons = extract_urls_and_favicons(documents)
                metadata = {
                    "search_count": doc_count,
                    "urls": urls,
                    "favicons": favicons,
                }
            else:
                metadata = {"search_count": doc_count}

            return StreamEventBuilder.status_update(
                phase=StreamPhase.RETRIEVAL,
                message=message,
                metadata=metadata,
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
