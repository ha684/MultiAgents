from typing import List, Optional
from src.common.types import Message
from src.services.types import Conversation
from src.db.repository.conversation import ConversationRepository
from src.utils.decorators import singleton
from src.exceptions.chat_exceptions import ConversationNotFoundError
from src.utils.logger_conf import logger
import uuid
from src.db.models.conversation import MessageStatus


@singleton
class ConversationService:
    """ConversationService is the backend to serve the conversation management"""

    def __init__(self):
        self.conv_repository = ConversationRepository()
        logger.info("Conversation Service initialized")

    async def create_conversation(self, app_name: str, user_id: str) -> Conversation:
        c = await self.conv_repository.create_conversation(app_name, user_id)
        return c

    async def get_conversation(
        self, conversation_id: uuid.UUID, user_id: str
    ) -> Conversation:
        conversation = await self.conv_repository.get_conversation(
            conversation_id, user_id
        )
        if not conversation:
            raise ConversationNotFoundError(conversation_id=conversation_id)
        return conversation

    async def list_messages(
        self, conversation_id: uuid.UUID, last_summarized_order: int | None = None
    ) -> Optional[List[Message]]:
        messages = await self.conv_repository.get_messages(
            conversation_id, last_summarized_order
        )
        return messages if messages is not None else []

    async def list_conversation(self, user_id: str) -> List[Conversation]:
        return await self.conv_repository.list_conversations(user_id)

    async def delete_conversation(
        self, conversation_id: uuid.UUID, user_id: str
    ) -> str:
        """Delete a conversation and all related data"""
        result = await self.conv_repository.delete_conversation(
            conversation_id, user_id
        )
        if not result:
            raise ConversationNotFoundError(conversation_id=conversation_id)
        return result

    async def add_messages(
        self, messages: List[Message], conversation_id: uuid.UUID
    ) -> List[str]:
        """Add multiple messages to the conversation"""
        return await self.conv_repository.add_messages(messages, conversation_id)

    async def update_conversation(
        self,
        conversation: Conversation,
        user_id: str,
    ) -> Conversation:
        """Update a conversation"""
        return await self.conv_repository.update_conversation(conversation, user_id)

    async def update_message_status(
        self,
        message_id: uuid.UUID,
        status: MessageStatus,
        error_details: str | None = None,
    ) -> bool:
        """Update message status"""
        return await self.conv_repository.update_message_status(
            message_id, status, error_details
        )
