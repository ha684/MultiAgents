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

    async def ainvoke(
        self, state: StateT, config_override: Optional[RunConfig] = None
    ) -> InvokeResult[StateT]:
        run_cfg = config_override or self.default_run_config()
        lg_config = run_cfg.as_langgraph_config()
        last_state: StateT = state

        try:
            async with asyncio.timeout(run_cfg.timeout_seconds):
                async for chunk in self.graph.astream(state, config=lg_config):
                    if "__end__" in chunk:
                        last_state = chunk["__end__"]
                    else:
                        for node_output in chunk.values():
                            if isinstance(node_output, dict):
                                last_state = {**last_state, **node_output}

                return InvokeResult(state=last_state, status="success")

        except RecursionError:
            logger.warning("Recursion limit - returning last valid state")
            return InvokeResult(state=last_state, status="recursion_limit")

        except asyncio.TimeoutError:
            logger.warning("Timeout - returning last valid state")
            return InvokeResult(state=last_state, status="timeout")

        except Exception as e:
            logger.error(f"Error - returning last valid state: {e}", exc_info=True)
            return InvokeResult(state=last_state, status="error", message=str(e))

    async def astream(
        self, state: StateT, config_override: Optional[RunConfig] = None
    ) -> AsyncGenerator[StreamEvent, None]:
        """Stream events - use for testing and monitoring"""
        run_cfg = config_override or self.default_run_config()
        # langfuse_handler = setup_langfuse()
        # run_cfg.extra["callbacks"] = [langfuse_handler]
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
