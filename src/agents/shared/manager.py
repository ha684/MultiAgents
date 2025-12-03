# src/agents/shared/manager.py

from src.domain.entities.graph import Execution
from src.utils.decorators import singleton


@singleton
class ExecutionManager:
    """Manage running graphs"""

    def __init__(self):
        self.executions: dict[str, Execution] = {}

    def start_execution(self, thread_id: str) -> Execution:
        """Start tracking an execution"""
        execution = Execution(thread_id=thread_id)
        self.executions[thread_id] = execution
        return execution

    def get_execution(self, thread_id: str) -> Execution | None:
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

    def get_all_running(self) -> dict[str, Execution]:
        """Debug: view all graphs running"""
        return self.executions.copy()


execution_manager = ExecutionManager()
