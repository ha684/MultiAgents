from typing import List, Optional
from src.common.types import Message
from src.services.types import Conversation
from src.db.repository.conversation import ConversationRepository
from src.utils.decorators import singleton
from src.utils.logger_conf import logger


@singleton
class ConversationService:
    """ConversationService is the backend to serve the conversation management"""

    def __init__(self):
        self.conv_repository = ConversationRepository()
        logger.info("ConversationService initialized")

    async def _create_conversation(self, app_name: str, user_id: str) -> Conversation:
        c = await self.conv_repository.create_conversation(app_name, user_id)
        return c

    async def _list_messages(self, conversation_id: str) -> Optional[List[Message]]:
        conversation = await self.conv_repository.get_conversation(conversation_id)
        if conversation:
            messages = await self.conv_repository.get_messages(conversation_id)
            return messages
        return conversation

    async def _list_conversation(self, user_id: str) -> List[Conversation]:
        return await self.conv_repository.list_conversations(user_id)

    async def _delete_conversation(self, conversation_id: str) -> str:
        """Delete a conversation and all related data"""
        result = await self.conv_repository.delete_conversation(conversation_id)
        return result

    async def add_message(self, message: Message, conversation_id: str) -> str:
        """Add a message to the conversation"""
        return await self.conv_repository.add_message(message, conversation_id)
