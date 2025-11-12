# src/agents/executors/deep_research.py
import asyncio
import contextvars

from src.agents.graph import research_graph
from src.agents.shared.manager import execution_manager
from src.domain.entities.graph import SubgraphOutput
from src.domain.entities.state import OrchestratorState, ResearchState
from src.utils.logger_conf import logger


async def _run_deep_research(
    state: OrchestratorState,
) -> SubgraphOutput:
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

    sub_coro = research_graph.ainvoke(research_state)

    ctx = contextvars.copy_context()
    research_task = ctx.run(lambda: asyncio.create_task(sub_coro))
    skip_task = ctx.run(lambda: asyncio.create_task(execution.skip_event.wait()))

    done, pending = await asyncio.wait(
        [research_task, skip_task], return_when=asyncio.FIRST_COMPLETED
    )

    for t in pending:
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass

    if execution.should_skip():
        logger.warning("User requested skip during research")
        if not research_task.done():
            research_task.cancel()
            try:
                await research_task
            except asyncio.CancelledError:
                pass
        result_state = execution.partial_state or {
            "accumulated_knowledge": "",
            "cited_documents": [],
            "response_metadata": {},
        }
        message = "Skipped by user."
    else:
        result_state = await research_task
        execution.update_partial_state(result_state)
        message = None

    accumulated_knowledge = result_state.state.get("accumulated_knowledge", "")
    cited_documents = result_state.state.get("cited_documents", [])
    has_content = bool(accumulated_knowledge or cited_documents)

    if result_state.status == "error" and not has_content:
        logger.error(f"DeepResearchGraph hard error: {result_state.message}")
        return SubgraphOutput(
            main_context="",
            cited_documents=[],
            response_metadata=result_state.state.get("response_metadata", {}),
            subgraph_error=(result_state.message or "DeepResearchGraph failed"),
        )
    elif result_state.status in ("timeout", "recursion_limit"):
        warning_msg = f"Research {result_state.status} but may have partial results"
        logger.warning(
            f"DeepResearchGraph {result_state.status} with {'content' if has_content else 'no content'}"
        )
        return SubgraphOutput(
            main_context=accumulated_knowledge,
            cited_documents=cited_documents,
            response_metadata={
                "status": result_state.status,
                "warning": warning_msg,
                "partial_results": has_content,
                **(result_state.state.get("response_metadata", {})),
            },
            subgraph_error=None if has_content else warning_msg,
        )
    else:
        return SubgraphOutput(
            main_context=accumulated_knowledge,
            cited_documents=cited_documents,
            response_metadata=result_state.state.get("response_metadata", {}),
            subgraph_error=message,
        )


class DeepResearchExecutor:
    async def __call__(self, state: OrchestratorState) -> SubgraphOutput:
        return await _run_deep_research(state)
