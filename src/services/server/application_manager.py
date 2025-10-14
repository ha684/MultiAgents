from abc import ABC, abstractmethod
from ...common.types import AgentCard, Message, Task
from ...services.types import Conversation, Event


class ApplicationManager(ABC):
    @abstractmethod
    async def create_conversation(self, user_id: str) -> Conversation:
        pass

    @abstractmethod
    def sanitize_message(self, message: Message) -> Message:
        pass

    @abstractmethod
    async def process_message(self, message: Message):
        pass

    @abstractmethod
    async def register_agent(self, url: str):
        pass

    @abstractmethod
    async def get_pending_messages(self) -> list[tuple[str, str]]:
        pass

    @abstractmethod
    async def list_conversations(self) -> list[Conversation]:
        pass

    @abstractmethod
    async def list_tasks(self) -> list[Task]:
        pass

    @property
    @abstractmethod
    def agents(self) -> list[AgentCard]:
        pass

    @abstractmethod
    async def get_events(self) -> list[Event]:
        pass

    @abstractmethod
    async def delete_conversation(self, conversation_id: str) -> bool:
        pass
