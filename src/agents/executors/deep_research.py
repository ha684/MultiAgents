# src/agents/executors/deep_research.py
import asyncio

from src.agents.graph.state import OrchestratorState, ResearchState
from src.agents.com.types import SubgraphOutput
from src.agents.graph import research_graph
from src.agents.com.manager import execution_manager
from src.utils.logger_conf import logger


async def _run_deep_research(state: OrchestratorState) -> SubgraphOutput:
    """Execute research subgraph"""
    context_metadata = state["conversation"][-1].additional_kwargs.get(
        "message_metadata", {}
    )
    research_state = ResearchState(
        contextualized_query=state["contextualized_query"],
        context_metadata=context_metadata,
    )
    execution = execution_manager.get_execution(
        state["conversation"][-1].additional_kwargs.get("conversation_id")
    )

    research_task = asyncio.create_task(research_graph.ainvoke(state=research_state))

    done, pending = await asyncio.wait(
        [research_task, asyncio.create_task(execution.skip_event.wait())],
        return_when=asyncio.FIRST_COMPLETED,
    )

    for task in pending:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    if execution.should_skip():
        logger.warning("User requested skip during research")
        result = execution.partial_state or {
            "accumulated_knowledge": "",
            "cited_documents": [],
        }
    else:
        result = await research_task
        execution.update_partial_state(result)

    return SubgraphOutput(
        main_context=result.state.get("accumulated_knowledge", ""),
        cited_documents=result.state.get("cited_documents", []),
        response_metadata=result.state.get("response_metadata", {}),
        subgraph_error=result.message,
    )


class DeepResearchExecutor:
    async def __call__(self, state: OrchestratorState) -> SubgraphOutput:
        return await _run_deep_research(state)
