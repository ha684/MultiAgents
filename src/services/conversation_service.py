from typing import Optional
from src.common.types import Message
from src.db.repository.conversation import ConversationRepository
from src.utils.decorators import singleton
from src.utils.logger_conf import logger
from src.services.types import (
    CreateConversationResponse,
    GetEventResponse,
    ListConversationResponse,
)


@singleton
class ConversationService:
    """ConversationService is the backend to serve the conversation management"""

    def __init__(self):
        self.conv_repository = ConversationRepository()
        logger.info("ConversationService initialized")

    async def _create_conversation(
        self, app_name: str, user_id: str
    ) -> CreateConversationResponse:
        c = await self.conv_repository.create_conversation(app_name, user_id)
        return CreateConversationResponse(result=c)

    async def _list_messages(self, conversation_id: str) -> list[Message]:
        conversation = await self.conv_repository.get_conversation(conversation_id)
        if conversation:
            messages = await self.conv_repository.get_messages(conversation_id)
            return messages
        return []

    async def _list_conversation(
        self, app_name: Optional[str], user_id: Optional[str]
    ) -> ListConversationResponse:
        result = await self.conv_repository.list_conversations(app_name, user_id)
        return ListConversationResponse(result=result)

    async def _get_events_all(self, conversation_id: Optional[str]) -> GetEventResponse:
        result = await self.conv_repository.get_events_all(
            conversation_id=conversation_id
        )
        return GetEventResponse(result=result)

    async def _delete_conversation(self, conversation_id: str) -> str:
        """Delete a conversation and all related data"""
        result = await self.conv_repository.delete_conversation(conversation_id)
        return (
            f"Conversation {conversation_id} deleted successfully"
            if result
            else f"Conversation {conversation_id} not found"
        )

    async def add_message(self, message: Message, conversation_id: str) -> str:
        """Add a message to the conversation"""
        return await self.conv_repository.add_message(message, conversation_id)
