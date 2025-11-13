# src/agents/graph/normal_graph.py
"""
Normal Graph - Fast Path for Straightforward Queries
Linear flow: Generate Direction → Execute Subgraph → Synthesize Response
"""

from typing import Any, Dict

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.basic import response_agent
from src.agents.executors import EXECUTORS
from src.agents.graph.base import GraphAgentBase
from src.agents.shared.registry import SubgraphRegistry
from src.domain.entities.graph import RunConfig, SubgraphOutput
from src.domain.entities.state import NormalGraphState
from src.utils import (
    format_context_for_response,
    normalize_url,
    truncate_docs_by_tokens,
)
from src.utils.logger_conf import logger
from src.agents.basic import reflection_agent
from src.domain.entities.graph import ResponseMode


class NormalGraph(GraphAgentBase[NormalGraphState]):
    """
    Normal Graph - Fast Path for Clear Queries

    Flow:
    1. Generate Direction: LLM selects subgraph + optimizes query
    2. Execute Subgraph: Run selected subgraph
    3. Synthesize Response: Generate final answer

    Single-shot execution, no iteration.
    """

    def __init__(self):
        super().__init__()
        self.graph_name = "NormalGraph"
        self.compiled_graph = self._build_graph()

    @property
    def graph(self) -> CompiledStateGraph:
        return self.compiled_graph

    def default_run_config(self) -> RunConfig:
        return RunConfig(
            graph_name=self.graph_name, recursion_limit=10, timeout_seconds=60
        )

    async def generate_direction_node(self, state: NormalGraphState) -> Dict[str, Any]:
        """
        Generate focused research direction for current depth level.
        Similar to ChatGPT's progressive thinking.
        """
        depth_level = state.get("current_depth_level", 0)
        query = state["contextualized_query"]

        try:
            resp, thinking_content = await reflection_agent.ainvoke(state=state)
            direction = resp.get("query", query)
            action = resp.get("action", "use_tool")
            selected_subgraph = resp.get("subgraph", "web_search")
            reasoning = resp.get("reasoning", "")
            thinking = (
                thinking_content
                if thinking_content
                else f"Exploring next aspect of: {query}"
            )
        except Exception as e:
            logger.error(f"Failed to generate direction: {e}")
            direction = query
            action = "use_tool"
            selected_subgraph = "web_search"
            reasoning = ""
            thinking = f"Continuing research on: {query}"

        logger.info(f"[Depth {depth_level}] {thinking}")
        logger.info(f"[Direction] {direction}")

        return {
            "current_direction": direction,
            "action": action,
            "selected_subgraph": selected_subgraph,
            "reasoning": reasoning,
            "thinking_notes": thinking,
        }

    async def execute_subgraph_node(self, state: NormalGraphState) -> Dict[str, Any]:
        """Execute selected subgraph and return documents."""
        subgraph_name = state.get("selected_subgraph")
        query = state.get("current_direction")

        if not subgraph_name:
            logger.error("[NormalGraph] No subgraph selected")
            return {"_temp_documents": []}

        try:
            subgraph_config = SubgraphRegistry.get_profile(subgraph_name)

            if not subgraph_config:
                logger.error(f"[NormalGraph] Subgraph '{subgraph_name}' not found")
                return {"_temp_documents": []}

            exec_ref = subgraph_config.executor
            executor = (
                EXECUTORS.get(exec_ref) if isinstance(exec_ref, str) else exec_ref
            )

            if not executor or not callable(executor):
                logger.error(
                    f"[NormalGraph] Executor for '{subgraph_name}' not callable"
                )
                return {"_temp_documents": []}

            execution_state = dict(state)
            execution_state["contextualized_query"] = query

            logger.info(f"[NormalGraph] Executing {subgraph_name}: {query}")

            result_obj: SubgraphOutput = await executor(execution_state)
            main_context = result_obj.main_context or ""
            cited_documents = result_obj.cited_documents or []

            if not main_context and cited_documents:
                main_context = format_context_for_response(cited_documents)

            logger.info(
                f"[NormalGraph] {subgraph_name} returned {len(cited_documents)} documents"
            )

            used_rag_ids = set(state.get("used_rag_ids", []))
            used_web_urls = set(state.get("used_web_urls", []))

            new_docs = []
            for doc in cited_documents:
                meta = doc.metadata
                doc_id = meta.get("document_id")
                url = normalize_url(meta)

                if doc_id and doc_id in used_rag_ids:
                    continue
                if url and url in used_web_urls:
                    continue

                new_docs.append(doc)
                if doc_id:
                    used_rag_ids.add(doc_id)
                if url:
                    used_web_urls.add(url)

            logger.info(
                f"[NormalGraph] {len(new_docs)}/{len(cited_documents)} new documents after dedup"
            )

            new_docs = truncate_docs_by_tokens(
                new_docs, max_tokens=8192, tokenizer=self.tokenizer
            )

            search_history = list(state.get("search_history", []))
            search_history.append(
                {
                    "subgraph": subgraph_name,
                    "query": query,
                    "doc_count": len(new_docs),
                    "depth_level": state.get("current_depth_level", 0),
                }
            )

            return {
                "_temp_documents": new_docs,
                "used_rag_ids": list(used_rag_ids),
                "used_web_urls": list(used_web_urls),
                "search_count": state.get("search_count", 0) + 1,
                "search_history": search_history,
            }

        except Exception as e:
            logger.error(f"[NormalGraph] Error executing {subgraph_name}: {e}")
            return {"_temp_documents": []}

    async def synthesize_response_node(self, state: NormalGraphState) -> Dict[str, Any]:
        """Synthesize final response using response_agent."""
        execution_error = state.get("execution_error")
        if execution_error:
            response_mode = ResponseMode.NO_VIABLE_OPTION
        elif state.get("selected_subgraph") == "sql_query":
            response_mode = ResponseMode.SQL_RESPONSE
        else:
            response_mode = ResponseMode.STANDARD

        response = await response_agent.ainvoke(state)

        response_metadata = state.get("response_metadata", {})
        response_metadata.update(
            {
                "mode": "normal",
                "subgraph": state.get("selected_subgraph"),
                "response_mode": response_mode,
            }
        )

        return {
            "final_answer": response.content,
            "response_metadata": response_metadata,
        }

    def _build_graph(self) -> CompiledStateGraph:
        """Build the normal graph workflow."""
        workflow = StateGraph(NormalGraphState)

        workflow.add_node("generate_direction", self.generate_direction_node)
        workflow.add_node("execute_subgraph", self.execute_subgraph_node)
        workflow.add_node("synthesize_response", self.synthesize_response_node)

        workflow.set_entry_point("generate_direction")
        workflow.add_edge("generate_direction", "execute_subgraph")
        workflow.add_edge("execute_subgraph", "synthesize_response")
        workflow.add_edge("synthesize_response", END)

        return workflow.compile(name=self.graph_name)
