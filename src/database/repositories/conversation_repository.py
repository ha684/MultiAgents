# src/database/repositories/conversation_repository.py
"""
Database service layer for handling all database operations
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.exc import SQLAlchemyError

from src.database.models.conversation import (
    ConversationModel,
    MessageModel,
    MessageStatus,
)
from src.dependencies.database_session import DatabaseSession
from src.domain.schemas.chat import (
    Conversation,
    DataPart,
    FileContent,
    FilePart,
    Message,
    Part,
    RetrievalContext,
    TextPart,
)
from src.utils.decorators import singleton
from src.utils.logger_conf import logger


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
    ) -> Conversation | None:
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
                result = Conversation(
                    conversation_id=str(conv_model.id),
                    is_active=conv_model.is_active,
                    name=conv_model.name,
                    summary=conv_model.summary,
                    summarized_up_to_message_order=conv_model.summarized_up_to_message_order,
                )
            return result

        except SQLAlchemyError as e:
            logger.error("Error getting conversation")
            raise e

    async def update_conversation_metadata(
        self,
        conversation_id: uuid.UUID,
        name: str,
        is_active: bool,
        user_id: str,
    ) -> Conversation:
        """Update user-controllable fields only"""
        try:
            async with DatabaseSession() as session:
                query = select(ConversationModel).filter_by(
                    id=conversation_id, user_id=user_id
                )
                result = await session.execute(query)
                conv_model = result.scalar_one_or_none()

                if not conv_model:
                    raise ValueError(f"Conversation {conversation_id} not found")

                conv_model.name = name
                conv_model.is_active = is_active
                conv_model.updated_at = datetime.now()

                await session.refresh(conv_model)

                return Conversation(
                    conversation_id=str(conv_model.id),
                    is_active=conv_model.is_active,
                    name=conv_model.name,
                    summary=conv_model.summary,
                    summarized_up_to_message_order=conv_model.summarized_up_to_message_order,
                )
        except SQLAlchemyError as e:
            logger.error(f"Error updating conversation metadata: {e}")
            raise

    async def update_conversation_summary(
        self,
        conversation_id: uuid.UUID,
        summary: str,
        summarized_up_to: int,
        user_id: str,
    ) -> Conversation:
        """Update summary fields only"""
        try:
            async with DatabaseSession() as session:
                query = select(ConversationModel).filter_by(
                    id=conversation_id, user_id=user_id
                )
                result = await session.execute(query)
                conv_model = result.scalar_one_or_none()

                if not conv_model:
                    raise ValueError(f"Conversation {conversation_id} not found")

                conv_model.summary = summary
                conv_model.summarized_up_to_message_order = summarized_up_to
                conv_model.updated_at = datetime.now()

                await session.refresh(conv_model)

                return Conversation(
                    conversation_id=str(conv_model.id),
                    is_active=conv_model.is_active,
                    name=conv_model.name,
                    summary=conv_model.summary,
                    summarized_up_to_message_order=conv_model.summarized_up_to_message_order,
                )
        except SQLAlchemyError as e:
            logger.error(f"Error updating conversation summary: {e}")
            raise

    async def list_conversations(self, user_id: str) -> list[Conversation]:
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

    async def add_messages(
        self, messages: list[Message], conversation_id: uuid.UUID
    ) -> list[str]:
        """Add multiple messages to the database in a single transaction"""
        try:
            async with DatabaseSession() as session:
                count_result = await session.execute(
                    select(MessageModel).filter_by(conversation_id=conversation_id)
                )
                max_order = len(count_result.scalars().all())

                message_ids = []
                message_models = []

                for idx, message in enumerate(messages):
                    status = (
                        MessageStatus.COMPLETED
                        if message.role == "agent"
                        else MessageStatus.COMPLETED
                    )

                    msg_model = MessageModel(
                        conversation_id=conversation_id,
                        role=message.role,
                        parts=self._serialize_parts(message.parts),
                        message_metadata=message.metadata,
                        message_order=max_order + idx + 1,
                        retrieval_context=(
                            message.retrieval_context.model_dump()
                            if message.retrieval_context
                            else None
                        ),
                        status=status,
                    )
                    message_models.append(msg_model)
                    session.add(msg_model)

                await session.flush()

                for msg_model in message_models:
                    message_ids.append(str(msg_model.id))

                return message_ids

        except SQLAlchemyError as e:
            logger.error(f"Error adding messages in batch: {e}")
            raise e

    async def get_messages(
        self, conversation_id: uuid.UUID, last_summarized_order: int | None = None
    ) -> list[Message]:
        """Get all messages for a conversation"""
        try:
            async with DatabaseSession() as session:
                query = (
                    select(MessageModel)
                    .filter_by(conversation_id=conversation_id)
                    .order_by(MessageModel.message_order.desc())
                    .limit(50)
                )
                if last_summarized_order:
                    query = query.where(
                        MessageModel.message_order > last_summarized_order
                    )
                result = await session.execute(query)
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

    def _serialize_parts(self, parts: list[Part]) -> list[dict[str, Any]]:
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

    def _deserialize_parts(self, parts_data: list[dict[str, Any]]) -> list[Part]:
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

    def _serialize_message(self, message: Message) -> dict[str, Any]:
        """Serialize a message to JSON"""
        return {
            "id": message.id,
            "role": message.role,
            "parts": self._serialize_parts(message.parts),
            "metadata": message.metadata,
            "retrieval_context": (
                message.retrieval_context.model_dump()
                if message.retrieval_context
                else None
            ),
        }

    def _deserialize_message(self, message_data: dict[str, Any] | None) -> Message:
        """Deserialize a message from JSON"""
        if message_data is None:
            return {}
        return Message(
            id=message_data["id"],
            role=message_data["role"],
            parts=self._deserialize_parts(message_data["parts"]),
            metadata=message_data.get("metadata"),
            retrieval_context=(
                RetrievalContext(**message_data.get("retrieval_context"))
                if message_data.get("retrieval_context")
                else None
            ),
        )

    def _model_to_message(self, msg_model: MessageModel) -> Message:
        """Convert MessageModel to Message"""
        msg_model.message_metadata["message_order"] = msg_model.message_order
        return Message(
            id=str(msg_model.id),
            role=msg_model.role,
            parts=self._deserialize_parts(msg_model.parts),
            metadata=msg_model.message_metadata,
            retrieval_context=(
                RetrievalContext(**msg_model.retrieval_context)
                if msg_model.retrieval_context
                else None
            ),
        )
