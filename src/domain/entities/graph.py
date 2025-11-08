# src/domain/entities/graph.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, Optional, List, Any, Protocol
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


@dataclass
class RoutingCondition:
    """
    Defines WHEN a subgraph should be activated.
    Inspired by Parlant's Guideline conditions.
    """

    trigger: str

    signals: List[str] = field(default_factory=list)

    requires_context: Optional[Dict[str, any]] = None

    exclude_when: List[str] = field(default_factory=list)


@dataclass
class RoutingAction:
    """
    Defines WHAT the subgraph does and HOW to route to it.
    Inspired by Parlant's Guideline actions.
    """

    capability: str

    router_instruction: str

    expected_outcome: str

    query_transformation: Optional[str] = None


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

    activation_conditions: List[str]

    typical_flow: List[str]

    digression_patterns: Dict[str, str] = field(default_factory=dict)

    prerequisites: List[str] = field(default_factory=list)


@dataclass
class SubgraphProfile:
    """
    Complete profile of a subgraph's capabilities and behavior.
    """

    name: str
    display_name: str

    primary_behavior: SubgraphBehavior

    secondary_behaviors: List[SubgraphBehavior] = field(default_factory=list)

    journeys: List[SubgraphJourney] = field(default_factory=list)

    glossary: Dict[str, str] = field(default_factory=dict)

    canonical_examples: List[Dict[str, str]] = field(default_factory=list)

    entry_state_type: Optional[type] = None
    executor: any = None

    tags: List[str] = field(default_factory=list)
    confidence_threshold: float = 0.7
