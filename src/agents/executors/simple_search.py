# src/agents/executors/simple_search.py
from typing import Any, Dict

from src.agents.graph import simple_search_graph
from src.agents.graph.state import OrchestratorState, SimpleSearchState
from src.domain.entities.graph import SubgraphOutput


def _prepare_web_metadata(state: OrchestratorState, web_active: bool) -> Dict[str, Any]:
    conv = list(state["conversation"])
    if not conv:
        raise ValueError("Conversation is empty.")

    last = conv[-1]
    addl = getattr(last, "additional_kwargs", {}) or {}
    meta = dict((addl.get("message_metadata") or {}))
    wsc = meta.get("web_search_config")

    if wsc is None and web_active:
        raise ValueError(
            "web_search_config is required for web search but was not found."
        )

    if wsc is not None:
        if isinstance(wsc, dict):
            wsc = {**wsc, "active": web_active}
        else:
            try:
                wsc = wsc.model_copy(update={"active": web_active})
            except AttributeError:
                wsc = wsc.copy(update={"active": web_active})

    meta["web_search_config"] = wsc
    addl["message_metadata"] = meta
    conv[-1] = type(last)(**{**last.__dict__, "additional_kwargs": addl})
    return {"conversation": conv}


async def _run_simple_search(
    state: OrchestratorState, web_active: bool
) -> SubgraphOutput:
    conv_update = _prepare_web_metadata(state, web_active)
    simple_search_state = SimpleSearchState(
        conversation=conv_update["conversation"],
        original_query=state["conversation"][-1].content,
        contextualized_query=state["contextualized_query"],
    )
    result = await simple_search_graph.ainvoke(state=simple_search_state)

    return SubgraphOutput(
        main_context="",
        cited_documents=result.state.get("cited_documents", []),
        response_metadata=result.state.get("response_metadata", {}),
        subgraph_error=result.message,
    )


class RagSearchExecutor:
    async def __call__(self, state: OrchestratorState) -> SubgraphOutput:
        return await _run_simple_search(state, web_active=False)


class WebSearchExecutor:
    async def __call__(self, state: OrchestratorState) -> SubgraphOutput:
        return await _run_simple_search(state, web_active=True)
