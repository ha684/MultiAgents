# src/services/conversation_service.py
import uuid

from src.core.exceptions.chat_exceptions import ConversationNotFoundError
from src.database.models.conversation import MessageStatus
from src.database.repositories.conversation_repository import ConversationRepository
from src.domain.schemas.chat import Conversation, Message
from src.domain.schemas.conversation import ConversationUpdate
from src.utils.decorators import singleton
from src.utils.logger_conf import logger


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
    ) -> list[Message] | None:
        messages = await self.conv_repository.get_messages(
            conversation_id, last_summarized_order
        )
        return messages if messages is not None else []

    async def list_conversation(self, user_id: str) -> list[Conversation]:
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
        self, messages: list[Message], conversation_id: uuid.UUID
    ) -> list[str]:
        """Add multiple messages to the conversation"""
        return await self.conv_repository.add_messages(messages, conversation_id)

    async def update_conversation_metadata(
        self,
        conversation_update: ConversationUpdate,
        user_id: str,
    ) -> Conversation:
        """Update user-controllable conversation fields"""
        return await self.conv_repository.update_conversation_metadata(
            conversation_id=conversation_update.conversation_id,
            name=conversation_update.name,
            is_active=conversation_update.is_active,
            user_id=user_id,
        )

    async def update_conversation_summary(
        self,
        conversation_id: uuid.UUID,
        summary: str,
        summarized_up_to: int,
        user_id: str,
    ) -> Conversation:
        """Update internal conversation summary"""
        return await self.conv_repository.update_conversation_summary(
            conversation_id=conversation_id,
            summary=summary,
            summarized_up_to=summarized_up_to,
            user_id=user_id,
        )

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
