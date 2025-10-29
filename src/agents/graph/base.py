# src/agents/graph/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass
from typing import AsyncGenerator, Generic, Literal, Optional, TypeVar

from langchain_core.runnables.schema import StreamEvent
from langgraph.graph.state import CompiledStateGraph

from src.agents.basic.base import BaseAgent
from src.domain.entities.graph import RunConfig
from src.utils.logger_conf import logger

StateT = TypeVar("StateT")
Status = Literal["success", "timeout", "recursion_limit", "error"]


@dataclass
class InvokeResult(Generic[StateT]):
    """
    Standardize the return result of the async graph node:
    - state: the final state after running the graph
    - status: the type of result (success, timeout, recursion_limit, error)
    - message: detailed context of error/success (used for logging or LLM)
    """

    state: StateT
    status: Status
    message: Optional[str] = None


class GraphAgentBase(BaseAgent, ABC, Generic[StateT]):
    """For agents running LangGraph; keep all run/stream/timeout logic here."""

    @property
    @abstractmethod
    def graph(self) -> CompiledStateGraph: ...

    @abstractmethod
    def default_run_config(self) -> RunConfig: ...

    def on_node_state(
        self, last_state: StateT, node_output: Optional[StateT]
    ) -> StateT:
        return node_output if node_output is not None else last_state

    async def ainvoke(
        self, state: StateT, config_override: Optional[RunConfig] = None
    ) -> InvokeResult[StateT]:
        """Invoke and return the final result - used for subgraph nodes"""
        run_cfg = config_override or self.default_run_config()
        lg_config = run_cfg.as_langgraph_config()
        last_state: StateT = state

        try:
            async with asyncio.timeout(run_cfg.timeout_seconds):
                async for event in self.graph.astream_events(
                    state, config=lg_config, version=run_cfg.version
                ):
                    out = event.get("data", {}).get("output")
                    last_state = self.on_node_state(last_state, out)

            return InvokeResult(state=last_state, status="success")

        except RecursionError:
            msg = (
                f"🛑 Graph '{run_cfg.graph_name}' stopped due to recursion limit "
                f"({run_cfg.recursion_limit}). Returning last known state. "
                f"Consider increasing recursion_limit or checking for circular dependencies."
            )
            logger.warning(msg)
            return InvokeResult(state=last_state, status="recursion_limit", message=msg)

        except asyncio.TimeoutError:
            msg = (
                f"⚠️ Graph '{run_cfg.graph_name}' timed out after "
                f"{run_cfg.timeout_seconds}s. Returning last known state. "
                f"Consider optimizing long-running nodes or increasing timeout_seconds."
            )
            logger.warning(msg)
            return InvokeResult(state=last_state, status="timeout", message=msg)

        except Exception as e:
            msg = (
                f"❌ Graph '{run_cfg.graph_name}' failed due to unexpected error "
                f"({type(e).__name__}: {e}). Returning last known state. "
                f"Review stack trace and node logic for root cause."
            )
            logger.error(msg, exc_info=True)
            return InvokeResult(state=last_state, status="error", message=msg)

    async def astream(
        self, state: StateT, config_override: Optional[RunConfig] = None
    ) -> AsyncGenerator[StreamEvent, None]:
        """Stream events - use for testing and monitoring"""
        run_cfg = config_override or self.default_run_config()
        lg_config = run_cfg.as_langgraph_config()
        last_state: StateT = state

        try:
            async with asyncio.timeout(run_cfg.timeout_seconds):
                async for event in self.graph.astream_events(
                    state, config=lg_config, version=run_cfg.version
                ):
                    last_state = event
                    yield event

        except asyncio.TimeoutError:
            logger.warning(
                f"⚠️ '{run_cfg.graph_name}' timed out after {run_cfg.timeout_seconds}s."
            )
            yield last_state
        except Exception as e:
            logger.error(
                f"❌ '{run_cfg.graph_name}' error: {e}.",
                exc_info=True,
            )
            yield last_state
