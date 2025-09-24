from typing import List, Optional
from src.common.types import Message
from src.services.types import Conversation
from src.db.repository.conversation import ConversationRepository
from src.utils.decorators import singleton
from src.exceptions.chat_exceptions import ConversationNotFoundError
from src.utils.logger_conf import logger
import uuid


@singleton
class ConversationService:
    """ConversationService is the backend to serve the conversation management"""

    def __init__(self):
        self.conv_repository = ConversationRepository()
        logger.info("Conversation Service initialized")

    async def create_conversation(self, app_name: str, user_id: str) -> Conversation:
        c = await self.conv_repository.create_conversation(app_name, user_id)
        return c

    async def list_messages(
        self, conversation_id: uuid.UUID, user_id: str
    ) -> Optional[List[Message]]:
        conversation = await self.conv_repository.get_conversation(
            conversation_id, user_id
        )
        if not conversation:
            raise ConversationNotFoundError(conversation_id=conversation_id)

        messages = await self.conv_repository.get_messages(conversation_id)
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

    async def add_message(self, message: Message, conversation_id: uuid.UUID) -> str:
        """Add a message to the conversation"""
        return await self.conv_repository.add_message(message, conversation_id)

    async def update_conversation(
        self, conversation_id: uuid.UUID, user_id: str, active: bool, name: str
    ) -> Conversation:
        """Update a conversation"""
        conversation = await self.conv_repository.get_conversation(
            conversation_id, user_id
        )
        if not conversation:
            raise ConversationNotFoundError(conversation_id=conversation_id)
        conversation.is_active = active
        conversation.name = name
        return await self.conv_repository.update_conversation(conversation, user_id)
