# src/agents/executors/simple_search.py
from src.agents.graph import simple_search_graph
from src.domain.entities.graph import SubgraphOutput
from src.domain.entities.state import SimpleSearchState


async def _run_simple_search(state: dict, web_active: bool) -> SubgraphOutput:
    simple_search_state = SimpleSearchState(
        conversation=state["conversation"],
        direction=state.get("direction", ""),
        seen_urls=set(state.get("seen_urls", set())),
        seen_doc_ids=set(state.get("seen_doc_ids", set())),
        duplicate_skip_ratio=state.get("duplicate_skip_ratio", 0.8),
        web_search_active=web_active,
    )

    result = await simple_search_graph.ainvoke(state=simple_search_state)

    res_state = (
        result.state
        if hasattr(result, "state") and isinstance(result.state, dict)
        else {}
    )

    cited_docs = res_state.get("cited_documents", [])
    has_content = bool(cited_docs)

    if result.status == "error" and not has_content:
        error_msg = getattr(result, "message", None) or "SimpleSearchGraph failed"
        return SubgraphOutput(
            main_context="",
            cited_documents=[],
            response_metadata={"error": error_msg, "status": result.status},
            subgraph_error=error_msg,
        )
    elif result.status in ("timeout", "recursion_limit"):
        warning_msg = f"Search {result.status} but may have partial results"
        return SubgraphOutput(
            main_context="",
            cited_documents=cited_docs,
            response_metadata={
                "status": result.status,
                "warning": warning_msg,
                "partial_results": has_content,
                **(res_state.get("response_metadata", {})),
            },
            subgraph_error=None if has_content else warning_msg,
        )
    else:
        return SubgraphOutput(
            main_context="",
            cited_documents=cited_docs,
            response_metadata=res_state.get("response_metadata", {}),
            subgraph_error=None,
        )


class RagSearchExecutor:
    async def __call__(self, state: dict) -> SubgraphOutput:
        return await _run_simple_search(state, web_active=False)


class WebSearchExecutor:
    async def __call__(self, state: dict) -> SubgraphOutput:
        return await _run_simple_search(state, web_active=True)
