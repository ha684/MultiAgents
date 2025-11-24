# src/domain/entities/graph.py
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol
from zoneinfo import ZoneInfo

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
    current_node: str | None = None
    partial_state: dict | None = None

    def should_skip(self) -> bool:
        return self.skip_event.is_set()

    def signal_skip(self):
        self.skip_event.set()

    def update_partial_state(self, state: dict):
        """Save current state to fallback when skip"""
        self.partial_state = state


@dataclass
class RunConfig:
    graph_name: str = "Graph"
    recursion_limit: int = 10
    timeout_seconds: int = 180
    version: str = "v2"
    extra: dict[str, Any] = field(default_factory=dict)

    def as_langgraph_config(self) -> dict[str, Any]:
        base = {"recursion_limit": self.recursion_limit}
        base.update(self.extra)
        return base


@dataclass
class SubgraphOutput:
    """Result of an execution"""

    main_context: str | None = None
    cited_documents: list[Document] | None = field(default_factory=list)
    response_metadata: dict[str, Any] | None = None
    subgraph_error: str | None = None


class SubgraphExecutor(Protocol):
    async def __call__(self, state: dict[str, Any]) -> SubgraphOutput: ...


class ResponseMode(str, Enum):
    """Modes for response_agent to handle different scenarios"""

    STANDARD = "standard"
    ADVANCE = "advance"
    SQL_RESPONSE = "sql_response"
    REASONING_ONLY = "reasoning_only"


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
    nodes: dict[str, NodeMetadata]
    default_message: str = "Processing..."

    def get_node_meta(self, node_name: str) -> NodeMetadata | None:
        """Get metadata for a node"""
        return self.nodes.get(node_name)


@dataclass
class RoutingCondition:
    """
    Defines WHEN a subgraph should be activated.
    Inspired by Parlant's Guideline conditions.
    """

    trigger: str

    signals: list[str] = field(default_factory=list)

    requires_context: dict[str, any] | None = None

    exclude_when: list[str] = field(default_factory=list)


@dataclass
class RoutingAction:
    """
    Defines WHAT the subgraph does and HOW to route to it.
    Inspired by Parlant's Guideline actions.
    """

    capability: str

    router_instruction: str

    expected_outcome: str

    query_transformation: str | None = None


@dataclass
class SubgraphBehavior:
    """
    A reusable behavioral pattern for subgraphs.
    Similar to Parlant's Guidelines but for routing decisions.
    """

    condition: RoutingCondition
    action: RoutingAction
    priority: int = 0

    def __str__(self):
        return f"WHEN {self.condition.trigger} THEN {self.action.capability}"


@dataclass
class SubgraphJourney:
    """
    Multi-step interaction patterns within a subgraph.
    Inspired by Parlant's Journeys but adapted for task delegation.
    """

    name: str
    description: str

    activation_conditions: list[str]

    typical_flow: list[str]

    digression_patterns: dict[str, str] = field(default_factory=dict)

    prerequisites: list[str] = field(default_factory=list)


@dataclass
class SubgraphProfile:
    """
    Complete profile of a subgraph's capabilities and behavior.
    """

    name: str
    display_name: str

    primary_behavior: SubgraphBehavior

    secondary_behaviors: list[SubgraphBehavior] = field(default_factory=list)

    journeys: list[SubgraphJourney] = field(default_factory=list)

    glossary: dict[str, str] = field(default_factory=dict)

    canonical_examples: list[dict[str, str]] = field(default_factory=list)

    entry_state_type: type | None = None
    executor: any = None

    tags: list[str] = field(default_factory=list)
