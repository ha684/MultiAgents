# src/agents/graph/base.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, TypeVar, Generic, AsyncGenerator
from abc import ABC, abstractmethod
import asyncio

from langgraph.graph.state import CompiledStateGraph
from langchain_core.runnables.schema import StreamEvent

from src.agents.basic.base import BaseAgent
from src.utils.logger_conf import logger

StateT = TypeVar("StateT")


@dataclass
class RunConfig:
    graph_name: str = "Graph"
    recursion_limit: int = 10
    timeout_seconds: int = 180
    version: str = "v2"
    extra: Dict[str, Any] = field(default_factory=dict)

    def as_langgraph_config(self) -> Dict[str, Any]:
        base = {"recursion_limit": self.recursion_limit}
        base.update(self.extra)
        return base


class GraphAgentBase(BaseAgent, ABC, Generic[StateT]):
    """For agents running LangGraph; keep all run/stream/timeout logic here."""

    @property
    @abstractmethod
    def graph(self) -> CompiledStateGraph: ...

    def default_run_config(self) -> RunConfig:
        return RunConfig(graph_name="Graph")

    def on_node_state(
        self, last_state: StateT, node_output: Optional[StateT]
    ) -> StateT:
        return node_output if node_output is not None else last_state

    async def ainvoke(
        self, state: StateT, config_override: Optional[RunConfig] = None
    ) -> StateT:
        """Invoke và trả về kết quả cuối cùng - dùng cho subgraph nodes"""
        run_cfg = config_override or self.default_run_config()
        lg_config = run_cfg.as_langgraph_config()
        last_state: StateT = state
        final_state: Optional[StateT] = None

        try:
            async with asyncio.timeout(run_cfg.timeout_seconds):
                async for event in self.graph.astream_events(
                    state, config=lg_config, version=run_cfg.version
                ):
                    kind = event.get("event")
                    name = event.get("name")

                    if kind == "on_chain_end" and name != run_cfg.graph_name:
                        out = event.get("data", {}).get("output")
                        last_state = self.on_node_state(last_state, out)

                    if kind == "on_chain_end" and name == run_cfg.graph_name:
                        final_state = event.get("data", {}).get("output")
                        if final_state is not None:
                            last_state = final_state

        except RecursionError:
            logger.warning(
                f"🛑 '{run_cfg.graph_name}' stopped (recursion_limit={run_cfg.recursion_limit}). Returning last_state."
            )
            return last_state
        except asyncio.TimeoutError:
            logger.warning(
                f"⚠️ '{run_cfg.graph_name}' timed out after {run_cfg.timeout_seconds}s. Returning last_state."
            )
            return last_state
        except Exception as e:
            logger.error(
                f"❌ '{run_cfg.graph_name}' error: {e}. Returning last_state.",
                exc_info=True,
            )
            return last_state

        return final_state if final_state is not None else last_state

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
