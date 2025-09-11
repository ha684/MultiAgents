import uuid

from collections.abc import Callable

from ...common.a2a_client import A2AClient
from ...common.types import (
    AgentCard,
    Task,
    TaskArtifactUpdateEvent,
    TaskSendParams,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)


TaskCallbackArg = Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent
TaskUpdateCallback = Callable[[TaskCallbackArg, AgentCard], Task]


class RemoteAgentConnections:
    """A class to hold the connections to the remote agents."""

    def __init__(self, agent_card: AgentCard):
        self.agent_client = A2AClient(agent_card, timeout=3600.0)
        self.card = agent_card

        self.conversation_name = None
        self.conversation = None
        self.pending_tasks = set()

    def get_agent(self) -> AgentCard:
        return self.card

    async def send_task(
        self,
        request: TaskSendParams,
        task_callback: TaskUpdateCallback | None,
    ) -> Task | None:
        response = await self.agent_client.send_task(request.model_dump())
        merge_metadata(response.result, request)
        if (
            hasattr(response.result, 'status')
            and hasattr(response.result.status, 'message')
            and response.result.status.message
        ):
            merge_metadata(response.result.status.message, request.message)
            m = response.result.status.message
            if not m.metadata:
                m.metadata = {}
            if 'message_id' in m.metadata:
                m.metadata['last_message_id'] = m.metadata['message_id']
            m.metadata['message_id'] = str(uuid.uuid4())

        if task_callback:
            await task_callback(response.result, self.card)
        return response.result


def merge_metadata(target : Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent, source : Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent):
    if not hasattr(target, 'metadata') or not hasattr(source, 'metadata'):
        return
    if target.metadata and source.metadata:
        target.metadata.update(source.metadata)
    elif source.metadata:
        target.metadata = dict(**source.metadata)