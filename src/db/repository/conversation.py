# src/db/repository/conversation.py
"""
Database service layer for handling all database operations
"""

from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import desc, select
from src.db.models.conversation import (
    ConversationModel,
    MessageModel,
)
from src.common.types import (
    Message,
    Part,
    TextPart,
    DataPart,
    FilePart,
    FileContent,
)
from src.services.types import Conversation
from src.utils.logger_conf import logger
from src.db.repository.database_session import DatabaseSession
from src.utils.decorators import singleton


@singleton
class ConversationRepository:
    """Service layer for all database operations"""

    async def create_conversation(self, app_name: str, user_id: str) -> Conversation:
        """Create a new conversation in the database"""
        try:
            async with DatabaseSession() as session:
                conv_model = ConversationModel(
                    name=app_name,
                    user_id=user_id,
                    is_active=True,
                )
                session.add(conv_model)
                await session.flush()
                await session.refresh(conv_model)
                result = Conversation(
                    conversation_id=str(conv_model.id), is_active=True, name=app_name
                )
            return result

        except SQLAlchemyError as e:
            logger.error(f"Error creating conversation: {e.args[0]}")
            raise e

    async def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Get a conversation by ID"""
        try:
            async with DatabaseSession() as session:
                query = select(ConversationModel).filter_by(id=conversation_id)
                result = await session.execute(query)
                conv_model = result.scalar_one_or_none()
                if not conv_model:
                    return None
                await session.flush()
                await session.refresh(conv_model)
                result = Conversation(
                    conversation_id=str(conv_model.id),
                    is_active=conv_model.is_active,
                    name=conv_model.name,
                )
            return result

        except SQLAlchemyError as e:
            logger.error(f"Error getting conversation: {e.args[0]}")
            raise e

    async def update_conversation(self, conversation: Conversation) -> Conversation:
        """Update a conversation"""
        try:
            async with DatabaseSession() as session:
                query = select(ConversationModel).filter_by(
                    id=conversation.conversation_id
                )

                result = await session.execute(query)
                conv_model = result.scalar_one_or_none()
                if conv_model:
                    conv_model.is_active = conversation.is_active
                    conv_model.name = conversation.name
                    conv_model.updated_at = datetime.now()
                await session.flush()
                await session.refresh(conv_model)
                result = Conversation(
                    conversation_id=str(conv_model.id),
                    is_active=conv_model.is_active,
                    name=conv_model.name,
                )
            return result
        except SQLAlchemyError as e:
            logger.error(f"Error updating conversation: {e.args[0]}")
            raise e

    async def list_conversations(self, user_id: str) -> List[Conversation]:
        """List all conversations, optionally filtered by app_name and user"""
        try:
            async with DatabaseSession() as session:
                query = select(ConversationModel)
                query = query.filter_by(user_id=user_id)
                query = query.order_by(desc(ConversationModel.updated_at))
                result = await session.execute(query)
                conv_models = result.scalars().all()

                conversations = []
                for conv_model in conv_models:
                    conversations.append(
                        Conversation(
                            conversation_id=str(conv_model.id),
                            is_active=conv_model.is_active,
                            name=conv_model.name,
                        )
                    )

            return conversations
        except SQLAlchemyError as e:
            logger.error(f"Error listing conversations: {e.args[0]}")
            raise e

    async def add_message(self, message: Message, conversation_id: str) -> str:
        """Add a message to the database"""
        try:
            async with DatabaseSession() as session:
                count_result = await session.execute(
                    select(MessageModel).filter_by(conversation_id=conversation_id)
                )
                max_order = len(count_result.scalars().all())
                msg_model = MessageModel(
                    conversation_id=conversation_id,
                    role=message.role,
                    parts=self._serialize_parts(message.parts),
                    message_metadata=message.metadata,
                    message_order=max_order + 1,
                )
                session.add(msg_model)

            return msg_model.id
        except SQLAlchemyError as e:
            logger.error(f"Error adding message: {e.args[0]}")
            raise e

    async def batch_add_messages(
        self, messages_with_conversations: List[Tuple[Message, str]]
    ) -> List[str]:
        """Batch insert multiple messages for better performance"""
        if not messages_with_conversations:
            return []

        try:
            async with DatabaseSession() as session:
                messages_by_conversation = {}
                for message, conv_id in messages_with_conversations:
                    if conv_id not in messages_by_conversation:
                        messages_by_conversation[conv_id] = []
                    messages_by_conversation[conv_id].append(message)

                bulk_data = []

                for conv_id, messages in messages_by_conversation.items():
                    count_result = await session.execute(
                        select(MessageModel).filter_by(conversation_id=conv_id)
                    )
                    max_order = len(count_result.scalars().all())

                    for i, message in enumerate(messages):
                        bulk_data.append(
                            {
                                "conversation_id": conv_id,
                                "role": message.role,
                                "parts": self._serialize_parts(message.parts),
                                "message_metadata": message.metadata,
                                "message_order": max_order + i + 1,
                            }
                        )

                if bulk_data:
                    await session.execute(MessageModel.__table__.insert(), bulk_data)
                    logger.info(f"Batch inserted {len(bulk_data)} messages")

            return [message.id for message in bulk_data]
        except SQLAlchemyError as e:
            logger.error(f"Error batch adding messages: {e.args[0]}")
            raise e

    async def get_messages(self, conversation_id: str) -> List[Message | None]:
        """Get all messages for a conversation"""
        try:
            async with DatabaseSession() as session:
                result = await session.execute(
                    select(MessageModel)
                    .filter_by(conversation_id=conversation_id)
                    .order_by(MessageModel.message_order)
                )
                messages = result.scalars().all()

            return [self._model_to_message(msg) for msg in messages]

        except SQLAlchemyError as e:
            logger.error(f"Error getting messages: {e.args[0]}")
            raise e

    async def get_conversation_with_messages(
        self, conversation_id: str
    ) -> Tuple[Optional[Conversation], List[Message]]:
        """Get conversation and its messages in a single transaction - reduces DB round trips"""
        try:
            async with DatabaseSession() as session:
                conv_query = select(ConversationModel).filter_by(id=conversation_id)

                conv_result = await session.execute(conv_query)
                conv_model = conv_result.scalar_one_or_none()
                if not conv_model:
                    return None, []

                msg_result = await session.execute(
                    select(MessageModel)
                    .filter_by(conversation_id=conversation_id)
                    .order_by(MessageModel.message_order)
                )
                messages = msg_result.scalars().all()

                conversation = Conversation(
                    conversation_id=conv_model.id,
                    is_active=conv_model.is_active,
                    name=conv_model.name,
                )

            return conversation, [self._model_to_message(msg) for msg in messages]
        except SQLAlchemyError as e:
            logger.error(f"Error getting conversation with messages: {e.args[0]}")
            raise e

    async def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation and all related data"""
        try:
            async with DatabaseSession() as session:
                query = select(ConversationModel).filter_by(id=conversation_id)
                result = await session.execute(query)
                conversation = result.scalar_one_or_none()
                if not conversation:
                    return False
                await session.delete(conversation)
                logger.info(
                    f"Deleted conversation {conversation_id} and all related data"
                )
            return True

        except SQLAlchemyError as e:
            logger.error(f"Error deleting conversation {conversation_id}: {e.args[0]}")
            raise e

    def _serialize_parts(self, parts: List[Part]) -> List[Dict[str, Any]]:
        """Serialize message parts to JSON"""
        serialized = []
        for part in parts:
            if part.type == "text":
                serialized.append({"type": "text", "text": part.text})
            elif part.type == "data":
                serialized.append({"type": "data", "data": part.data})
            elif part.type == "file":
                file_data = {}
                if part.file:
                    file_data = {
                        "uri": part.file.uri,
                        "bytes": part.file.bytes,
                        "mimeType": part.file.mimeType,
                        "name": part.file.name,
                    }
                serialized.append(
                    {
                        "type": "file",
                        "file": file_data,
                        "uri": part.file.uri,
                        "bytes": part.file.bytes,
                        "mimeType": part.file.mimeType,
                    }
                )
        return serialized

    def _deserialize_parts(self, parts_data: List[Dict[str, Any]]) -> List[Part]:
        """Deserialize parts from JSON"""
        parts = []
        for part_data in parts_data:
            if part_data["type"] == "text":
                parts.append(TextPart(text=part_data["text"]))
            elif part_data["type"] == "data":
                parts.append(DataPart(data=part_data["data"]))
            elif part_data["type"] == "file":
                file_content = None
                if "file" in part_data and part_data["file"]:
                    file_content = FileContent(**part_data["file"])
                parts.append(
                    FilePart(
                        file=file_content,
                        uri=part_data.get("uri"),
                        bytes=part_data.get("bytes"),
                        mimeType=part_data.get("mimeType"),
                    )
                )
        return parts

    def _serialize_message(self, message: Message) -> Dict[str, Any]:
        """Serialize a message to JSON"""
        return {
            "role": message.role,
            "parts": self._serialize_parts(message.parts),
            "metadata": message.metadata,
        }

    def _deserialize_message(self, message_data: Optional[Dict[str, Any]]) -> Message:
        """Deserialize a message from JSON"""
        if message_data is None:
            return {}
        return Message(
            role=message_data["role"],
            parts=self._deserialize_parts(message_data["parts"]),
            metadata=message_data.get("metadata"),
        )

    def _model_to_message(self, msg_model: MessageModel) -> Message:
        """Convert MessageModel to Message"""
        return Message(
            role=msg_model.role,
            parts=self._deserialize_parts(msg_model.parts),
            metadata=msg_model.message_metadata,
        )
