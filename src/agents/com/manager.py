# src/agents/com/manager.py
import asyncio
from typing import Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from src.utils.decorators import singleton


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


@singleton
class ExecutionManager:
    """Manage running graphs"""

    def __init__(self):
        self.executions: Dict[str, Execution] = {}

    def start_execution(self, thread_id: str) -> Execution:
        """Start tracking an execution"""
        execution = Execution(thread_id=thread_id)
        self.executions[thread_id] = execution
        return execution

    def get_execution(self, thread_id: str) -> Optional[Execution]:
        """Get running execution"""
        return self.executions.get(thread_id)

    def skip_research(self, thread_id: str) -> bool:
        """User request to skip research"""
        execution = self.executions.get(thread_id)
        if execution:
            execution.signal_skip()
            return True
        return False

    def finish_execution(self, thread_id: str):
        """Cleanup after finished"""
        self.executions.pop(thread_id, None)

    def get_all_running(self) -> Dict[str, Execution]:
        """Debug: view all graphs running"""
        return self.executions.copy()


execution_manager = ExecutionManager()
