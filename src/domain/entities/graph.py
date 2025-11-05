# src/domain/entities/graph.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, Optional, List, Type, Any, Protocol, Union
import asyncio
from enum import Enum

from langchain_core.documents import Document

from src.domain.schemas.stream import StreamPhase


@dataclass
class Execution:
    """Track an execution"""

    thread_id: str
    started_at: datetime = field(
        default_factory=lambda: datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    )
    skip_event: asyncio.Event = field(default_factory=asyncio.Event)
    current_node: Optional[str] = None
    partial_state: Optional[Dict] = None

    def should_skip(self) -> bool:
        return self.skip_event.is_set()

    def signal_skip(self):
        self.skip_event.set()

    def update_partial_state(self, state: Dict):
        """Save current state to fallback when skip"""
        self.partial_state = state


@dataclass
class SubgraphConfig:
    """Configuration for registering a subgraph as a tool"""

    name: str
    description: str
    when_to_use: str
    examples: List[str]
    entry_state_type: Type
    executor: Union[str, SubgraphExecutor]

    query_indicators: Optional[List[str]] = None
    not_suitable_for: Optional[List[str]] = None


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


@dataclass
class SubgraphOutput:
    """Result of an execution"""

    main_context: Optional[str] = None
    cited_documents: Optional[List[Document]] = field(default_factory=list)
    response_metadata: Optional[Dict[str, Any]] = None
    subgraph_error: Optional[str] = None


class SubgraphExecutor(Protocol):
    async def __call__(self, state: Dict[str, Any]) -> SubgraphOutput: ...


class ResponseMode(str, Enum):
    """Modes for response_agent to handle different scenarios"""

    ADVANCE = "advance"
    STANDARD = "standard"
    CHITCHAT = "chitchat"
    FOLLOWUP = "followup"
    NO_VIABLE_OPTION = "no_viable_option"
    ERROR = "error"
    SQL_RESPONSE = "sql_response"


@dataclass
class NodeMetadata:
    """Metadata for a single node"""

    display_message: str
    stream_phase: StreamPhase
    show_in_ui: bool = True
    emit_on_complete: bool = False


@dataclass
class GraphMetadata:
    """Configuration for a graph"""

    name: str
    nodes: Dict[str, NodeMetadata]
    default_message: str = "Processing..."

    def get_node_meta(self, node_name: str) -> Optional[NodeMetadata]:
        """Get metadata for a node"""
        return self.nodes.get(node_name)
