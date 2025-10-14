# src/db/repository/conversation.py
"""
Database service layer for handling all database operations
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
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
    RetrievalContext,
)
from src.services.types import Conversation
from src.utils.logger_conf import logger
from src.db.repository.database_session import DatabaseSession
from src.utils.decorators import singleton
import uuid
from src.db.models.conversation import MessageStatus


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

    async def get_conversation(
        self, conversation_id: uuid.UUID, user_id: str
    ) -> Optional[Conversation]:
        """Get a conversation by ID"""
        try:
            async with DatabaseSession() as session:
                query = select(ConversationModel).filter_by(
                    id=conversation_id, user_id=user_id
                )
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
            logger.error("Error getting conversation")
            raise e

    async def update_conversation(
        self, conversation: Conversation, user_id: str
    ) -> Conversation:
        """Update a conversation"""
        try:
            async with DatabaseSession() as session:
                query = select(ConversationModel).filter_by(
                    id=conversation.conversation_id, user_id=user_id
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
            logger.error("Error listing conversations")
            raise e

    async def add_message(
        self, message: Message, conversation_id: uuid.UUID
    ) -> str | None:
        """Add a message to the database"""
        try:
            async with DatabaseSession() as session:
                count_result = await session.execute(
                    select(MessageModel).filter_by(conversation_id=conversation_id)
                )
                status = (
                    MessageStatus.COMPLETED
                    if message.role == "agent"
                    else MessageStatus.PROCESSING
                )
                max_order = len(count_result.scalars().all())
                msg_model = MessageModel(
                    conversation_id=conversation_id,
                    role=message.role,
                    parts=self._serialize_parts(message.parts),
                    message_metadata=message.metadata,
                    message_order=max_order + 1,
                    retrieval_context=message.retrieval_context.model_dump()
                    if message.retrieval_context
                    else None,
                    status=status,
                )
                session.add(msg_model)

            return str(msg_model.id)
        except SQLAlchemyError as e:
            logger.error("Error adding message")
            raise e

    async def get_messages(self, conversation_id: uuid.UUID) -> List[Message]:
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
            logger.error("Error getting messages")
            raise e

    async def delete_conversation(
        self, conversation_id: uuid.UUID, user_id: str
    ) -> bool:
        """Delete a conversation and all related data"""
        try:
            async with DatabaseSession() as session:
                query = select(ConversationModel).filter_by(
                    id=conversation_id, user_id=user_id
                )
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
            logger.error(f"Error deleting conversation {conversation_id}")
            raise e

    async def update_message_status(
        self,
        message_id: uuid.UUID,
        status: MessageStatus,
        error_details: str | None = None,
    ) -> bool:
        """Update message status"""
        try:
            async with DatabaseSession() as session:
                query = select(MessageModel).filter_by(id=message_id)
                result = await session.execute(query)
                message = result.scalar_one_or_none()
                if not message:
                    return False
                message.status = status
                message.error_details = error_details
                await session.flush()
                await session.refresh(message)
            return True
        except SQLAlchemyError as e:
            logger.error(f"Error updating message status {message_id}")
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
            "id": message.id,
            "role": message.role,
            "parts": self._serialize_parts(message.parts),
            "metadata": message.metadata,
            "retrieval_context": message.retrieval_context.model_dump()
            if message.retrieval_context
            else None,
        }

    def _deserialize_message(self, message_data: Optional[Dict[str, Any]]) -> Message:
        """Deserialize a message from JSON"""
        if message_data is None:
            return {}
        return Message(
            id=message_data["id"],
            role=message_data["role"],
            parts=self._deserialize_parts(message_data["parts"]),
            metadata=message_data.get("metadata"),
            retrieval_context=RetrievalContext(**message_data.get("retrieval_context"))
            if message_data.get("retrieval_context")
            else None,
        )

    def _model_to_message(self, msg_model: MessageModel) -> Message:
        """Convert MessageModel to Message"""
        return Message(
            id=str(msg_model.id),
            role=msg_model.role,
            parts=self._deserialize_parts(msg_model.parts),
            metadata=msg_model.message_metadata,
            retrieval_context=RetrievalContext(**msg_model.retrieval_context)
            if msg_model.retrieval_context
            else None,
        )
