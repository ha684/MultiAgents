"""
Database service layer for handling all database operations
"""

import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import desc, delete, select
from sqlalchemy.orm import selectinload
import copy
from src.db.models.conversation import (
    ConversationModel,
    MessageModel,
    TaskModel,
    TaskStatusModel,
    TaskArtifactModel,
    TaskHistoryModel,
    ArtifactChunkModel,
    TaskMappingModel,
    NextIdMappingModel,
)
from src.common.types import (
    Message,
    Task,
    TaskStatus,
    Part,
    TextPart,
    DataPart,
    FilePart,
    FileContent,
    TaskState,
)
from src.services.types import Conversation
from google.adk.sessions.state import State
from google.adk.sessions.database_session_service import StorageEvent
from src.utils.logger_conf import logger
from .database_session import DatabaseSession
from src.utils.decorators import singleton


@singleton
class ConversationRepository:
    """Service layer for all database operations"""

    async def add_artifact_chunk(
        self, task_id: str, index: int, data: Dict[str, Any]
    ) -> str:
        """Add an artifact chunk"""
        try:
            async with DatabaseSession() as session:
                chunk_id = str(uuid.uuid4())
                chunk = ArtifactChunkModel(
                    id=chunk_id, task_id=task_id, index=index, data=data
                )
                session.add(chunk)
                await session.commit()
            return chunk_id
        except SQLAlchemyError as e:
            logger.error(f"Error adding artifact chunk: {e.args[0]}")
            raise e

    async def get_artifact_chunks(self, task_id: str) -> Dict[int, Dict[str, Any]]:
        """Get all artifact chunks for a task"""
        try:
            async with DatabaseSession() as session:
                result = await session.execute(
                    select(ArtifactChunkModel).filter_by(task_id=task_id)
                )
                chunks = result.scalars().all()
            return {chunk.index: chunk.data for chunk in chunks}
        except SQLAlchemyError as e:
            logger.error(f"Error getting artifact chunks: {e.args[0]}")
            raise e

    async def remove_artifact_chunk(self, task_id: str, index: int):
        """Remove an artifact chunk"""
        try:
            async with DatabaseSession() as session:
                await session.execute(
                    delete(ArtifactChunkModel).where(
                        ArtifactChunkModel.task_id == task_id,
                        ArtifactChunkModel.index == index,
                    )
                )
        except SQLAlchemyError as e:
            logger.error(f"Error removing artifact chunk: {e.args[0]}")
            raise e

    async def add_next_id_mapping(self, last_message_id: str, next_message_id: str):
        """Add a next ID mapping"""
        try:
            async with DatabaseSession() as session:
                mapping = NextIdMappingModel(
                    last_message_id=last_message_id, next_message_id=next_message_id
                )
                await session.merge(mapping)
        except SQLAlchemyError as e:
            logger.error(f"Error adding next ID mapping: {e.args[0]}")
            raise e

    async def add_task_mapping(self, message_id: str, task_id: str):
        """Add a message to task mapping"""
        try:
            async with DatabaseSession() as session:
                mapping = TaskMappingModel(message_id=message_id, task_id=task_id)
                await session.merge(mapping)
        except SQLAlchemyError as e:
            logger.error(f"Error adding task mapping: {e.args[0]}")
            raise e

    async def get_task_id_for_message(self, message_id: str) -> Optional[str]:
        """Get task ID for a message"""
        try:
            async with DatabaseSession() as session:
                result = await session.execute(
                    select(TaskMappingModel).filter_by(message_id=message_id)
                )
                mapping = result.scalar_one_or_none()
            return mapping.task_id if mapping else None
        except SQLAlchemyError as e:
            logger.error(f"Error getting task ID for message: {e.args[0]}")
            raise e

    async def create_conversation(
        self, conversation_id: str, app_name: str, user_id: str
    ) -> Conversation:
        """Create a new conversation in the database"""
        try:
            async with DatabaseSession() as session:
                conv_model = ConversationModel(
                    id=conversation_id,
                    app_name=app_name,
                    user_id=user_id,
                    is_active=True,
                    task_ids=[],
                )
                session.add(conv_model)

            return Conversation(
                conversation_id=conversation_id, is_active=True, name="", task_ids=[]
            )

        except SQLAlchemyError as e:
            logger.error(f"Error creating conversation: {e.args[0]}")
            raise e

    async def get_conversation(
        self, conversation_id: str, app_name: Optional[str] = None
    ) -> Optional[Conversation]:
        """Get a conversation by ID"""
        try:
            async with DatabaseSession() as session:
                query = select(ConversationModel).filter_by(id=conversation_id)
                if app_name:
                    query = query.filter_by(app_name=app_name)
                result = await session.execute(query)
                conv_model = result.scalar_one_or_none()
                if not conv_model:
                    return None

            return Conversation(
                conversation_id=conv_model.id,
                is_active=conv_model.is_active,
                name=conv_model.name,
                task_ids=conv_model.task_ids or [],
            )

        except SQLAlchemyError as e:
            logger.error(f"Error getting conversation: {e.args[0]}")
            raise e

    async def update_conversation(
        self, conversation: Conversation, app_name: Optional[str] = None
    ):
        """Update a conversation"""
        try:
            async with DatabaseSession() as session:
                query = select(ConversationModel).filter_by(
                    id=conversation.conversation_id
                )
                if app_name:
                    query = query.filter_by(app_name=app_name)

                result = await session.execute(query)
                conv_model = result.scalar_one_or_none()
                if conv_model:
                    conv_model.is_active = conversation.is_active
                    conv_model.name = conversation.name
                    conv_model.task_ids = conversation.task_ids
                    conv_model.updated_at = datetime.now()
        except SQLAlchemyError as e:
            logger.error(f"Error updating conversation: {e.args[0]}")
            raise e

    async def list_conversations(
        self, app_name: Optional[str] = None, user_id: Optional[str] = None
    ) -> List[Conversation]:
        """List all conversations, optionally filtered by app_name and user"""
        try:
            async with DatabaseSession() as session:
                query = select(ConversationModel)
                if app_name:
                    query = query.filter_by(app_name=app_name)
                if user_id:
                    query = query.filter_by(user_id=user_id)

                query = query.order_by(desc(ConversationModel.updated_at))
                result = await session.execute(query)
                conv_models = result.scalars().all()

                conversations = []
                for conv_model in conv_models:
                    conversations.append(
                        Conversation(
                            conversation_id=conv_model.id,
                            is_active=conv_model.is_active,
                            name=conv_model.name,
                            task_ids=conv_model.task_ids or [],
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

                message_id = (
                    message.metadata.get("message_id") if message.metadata else None
                )
                if not message_id:
                    message_id = str(uuid.uuid4())

                msg_model = MessageModel(
                    id=message_id,
                    conversation_id=conversation_id,
                    role=message.role,
                    parts=self._serialize_parts(message.parts),
                    message_metadata=message.metadata,
                    message_order=max_order + 1,
                )
                session.add(msg_model)

            return message_id
        except SQLAlchemyError as e:
            logger.error(f"Error adding message: {e.args[0]}")
            raise e

    async def batch_add_messages(
        self, messages_with_conversations: List[Tuple[Message, str]]
    ) -> List[str]:
        """Batch insert multiple messages for better performance"""
        if not messages_with_conversations:
            return []

        message_ids = []
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
                        message_id = (
                            message.metadata.get("message_id")
                            if message.metadata
                            else None
                        )
                        if not message_id:
                            message_id = str(uuid.uuid4())

                        message_ids.append(message_id)

                        bulk_data.append(
                            {
                                "id": message_id,
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

            return message_ids
        except SQLAlchemyError as e:
            logger.error(f"Error batch adding messages: {e.args[0]}")
            raise e

    async def get_messages(self, conversation_id: str) -> List[Message]:
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
        self, conversation_id: str, app_name: Optional[str] = None
    ) -> Tuple[Optional[Conversation], List[Message]]:
        """Get conversation and its messages in a single transaction - reduces DB round trips"""
        try:
            async with DatabaseSession() as session:
                conv_query = select(ConversationModel).filter_by(id=conversation_id)
                if app_name:
                    conv_query = conv_query.filter_by(app_name=app_name)

                conv_result = await session.execute(conv_query)
                conv_model = conv_result.scalar_one_or_none()
                if not conv_model:
                    return None, []

                # Get messages
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
                    task_ids=conv_model.task_ids or [],
                )

            return conversation, [self._model_to_message(msg) for msg in messages]
        except SQLAlchemyError as e:
            logger.error(f"Error getting conversation with messages: {e.args[0]}")
            raise e

    async def add_task(self, task: Task):
        """Add or update a task with split data structure"""
        try:
            async with DatabaseSession() as session:
                existing_result = await session.execute(
                    select(TaskModel).filter_by(id=task.id)
                )
                existing = existing_result.scalar_one_or_none()

                status_state = (
                    task.status.get("state", "unknown")
                    if isinstance(task.status, dict)
                    else "unknown"
                )
                status_message = (
                    task.status.get("message", {})
                    .get("parts", [{}])[0]
                    .get("text", "")[:500]
                    if isinstance(task.status, dict)
                    else ""
                )

                task_data = {
                    "id": task.id,
                    "conversation_id": task.sessionId,
                    "status_state": status_state,
                    "status_message": status_message,
                    "task_metadata": task.metadata,
                }

                if existing:
                    for key, value in task_data.items():
                        if key != "id":
                            setattr(existing, key, value)
                    existing.updated_at = datetime.now()

                    if existing.status_details:
                        existing.status_details.full_status = (
                            self._serialize_task_status(task.status)
                        )
                    else:
                        status_detail = TaskStatusModel(
                            task_id=task.id,
                            full_status=self._serialize_task_status(task.status),
                        )
                        session.add(status_detail)

                    await session.execute(
                        delete(TaskArtifactModel).where(
                            TaskArtifactModel.task_id == task.id
                        )
                    )
                    for i, artifact in enumerate(task.artifacts or []):
                        artifact_model = TaskArtifactModel(
                            id=f"{task.id}_artifact_{i}",
                            task_id=task.id,
                            artifact_data=self._serialize_artifact(artifact),
                            sequence_order=i,
                        )
                        session.add(artifact_model)

                    await session.execute(
                        delete(TaskHistoryModel).where(
                            TaskHistoryModel.task_id == task.id
                        )
                    )
                    for i, message in enumerate(task.history or []):
                        history_model = TaskHistoryModel(
                            id=f"{task.id}_history_{i}",
                            task_id=task.id,
                            history_data=self._serialize_message(message),
                            sequence_order=i,
                        )
                        session.add(history_model)
                else:
                    task_model = TaskModel(**task_data)
                    session.add(task_model)

                    status_detail = TaskStatusModel(
                        task_id=task.id,
                        full_status=self._serialize_task_status(task.status),
                    )
                    session.add(status_detail)

                    for i, artifact in enumerate(task.artifacts or []):
                        artifact_model = TaskArtifactModel(
                            id=f"{task.id}_artifact_{i}",
                            task_id=task.id,
                            artifact_data=self._serialize_artifact(artifact),
                            sequence_order=i,
                        )
                        session.add(artifact_model)

                    for i, message in enumerate(task.history or []):
                        history_model = TaskHistoryModel(
                            id=f"{task.id}_history_{i}",
                            task_id=task.id,
                            history_data=self._serialize_message(message),
                            sequence_order=i,
                        )
                        session.add(history_model)
        except SQLAlchemyError as e:
            logger.error(f"Error adding task: {e.args[0]}")
            raise e

    async def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID"""
        try:
            async with DatabaseSession() as session:
                result = await session.execute(
                    select(TaskModel)
                    .options(
                        selectinload(TaskModel.status_details),
                        selectinload(TaskModel.artifacts),
                        selectinload(TaskModel.history_items),
                    )
                    .filter_by(id=task_id)
                )
                task_model = result.scalar_one_or_none()
                if not task_model:
                    return None

            return self._model_to_task(task_model)
        except SQLAlchemyError as e:
            logger.error(f"Error getting task: {e.args[0]}")
            raise e

    async def list_tasks(self, conversation_id: Optional[str] = None) -> List[Task]:
        """List all tasks, optionally filtered by conversation"""
        try:
            async with DatabaseSession() as session:
                query = select(TaskModel).options(
                    selectinload(TaskModel.status_details),
                    selectinload(TaskModel.artifacts),
                    selectinload(TaskModel.history_items),
                )
                if conversation_id:
                    query = query.filter_by(conversation_id=conversation_id)

                query = query.order_by(desc(TaskModel.updated_at))
                result = await session.execute(query)
                tasks = result.scalars().all()

            return [self._model_to_task(t) for t in tasks]
        except SQLAlchemyError as e:
            logger.error(f"Error listing tasks: {e.args[0]}")
            raise e

    async def get_events_all(self, conversation_id: Optional[str] = None) -> List[Any]:
        """Get all events"""
        try:
            async with DatabaseSession() as session:
                query = select(StorageEvent)
                if conversation_id:
                    query = query.filter_by(session_id=conversation_id)

                query = query.order_by(StorageEvent.timestamp)
                result = await session.execute(query)
                event_models = result.scalars().all()

                events = []
                for event_model in event_models:
                    event_dict = {
                        "id": event_model.id,
                        "actor": event_model.author,
                        "content": event_model.content,
                        "timestamp": event_model.timestamp,
                    }
                    events.append(event_dict)

            return events
        except SQLAlchemyError as e:
            logger.error(f"Error getting events: {e.args[0]}")
            raise e

    async def delete_conversation(
        self, conversation_id: str, app_name: Optional[str] = None
    ) -> bool:
        """Delete a conversation and all related data"""
        try:
            async with DatabaseSession() as session:
                query = select(ConversationModel).filter_by(id=conversation_id)
                if app_name:
                    query = query.filter_by(app_name=app_name)

                result = await session.execute(query)
                conversation = result.scalar_one_or_none()
                if not conversation:
                    return False

                await session.delete(conversation)

                events_result = await session.execute(
                    select(StorageEvent).filter_by(session_id=conversation_id)
                )
                storage_events = events_result.scalars().all()
                for event in storage_events:
                    await session.delete(event)

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
                        "uri": part.uri,
                        "bytes": part.bytes,
                        "mimeType": part.mimeType,
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

    def _serialize_task_status(self, status: TaskStatus) -> Dict[str, Any]:
        """Serialize task status to JSON"""
        return {
            "state": status.state.value,
            "message": self._serialize_message(status.message)
            if status.message
            else None,
            "timestamp": status.timestamp.isoformat(),
        }

    def _deserialize_task_status(self, status_data: Dict[str, Any]) -> TaskStatus:
        """Deserialize task status from JSON"""
        message = None
        if status_data.get("message"):
            message = self._deserialize_message(status_data["message"])

        return TaskStatus(
            state=TaskState(status_data["state"]),
            message=message,
            timestamp=datetime.fromisoformat(status_data["timestamp"]),
        )

    def _serialize_artifact(self, artifact: Any) -> Dict[str, Any]:
        """Serialize an artifact to JSON"""
        return {
            "id": getattr(artifact, "id", None),
            "index": getattr(artifact, "index", None),
            "parts": self._serialize_parts(getattr(artifact, "parts", [])),
            "append": getattr(artifact, "append", False),
            "lastChunk": getattr(artifact, "lastChunk", True),
        }

    def _model_to_message(self, msg_model: MessageModel) -> Message:
        """Convert MessageModel to Message"""
        return Message(
            role=msg_model.role,
            parts=self._deserialize_parts(msg_model.parts),
            metadata=msg_model.message_metadata,
        )

    def _model_to_task(self, task_model: TaskModel) -> Task:
        """Convert TaskModel to Task"""
        artifacts = []
        if task_model.artifacts:
            for artifact_model in sorted(
                task_model.artifacts, key=lambda x: x.sequence_order
            ):
                artifacts.append(artifact_model.artifact_data)

        history = []
        if task_model.history_items:
            for history_model in sorted(
                task_model.history_items, key=lambda x: x.sequence_order
            ):
                history.append(self._deserialize_message(history_model.history_data))

        status = None
        if task_model.status_details:
            status = self._deserialize_task_status(
                task_model.status_details.full_status
            )
        else:
            status = {
                "state": task_model.status_state,
                "message": task_model.status_message,
                "timestamp": task_model.created_at.isoformat(),
            }

        return Task(
            id=task_model.id,
            sessionId=task_model.conversation_id,
            status=status,
            artifacts=artifacts if artifacts else None,
            history=history if history else None,
            metadata=task_model.task_metadata,
        )


def _extract_state_delta(state: dict[str, Any]):
    app_state_delta = {}
    user_state_delta = {}
    session_state_delta = {}
    if state:
        for key in state.keys():
            if key.startswith(State.APP_PREFIX):
                app_state_delta[key.removeprefix(State.APP_PREFIX)] = state[key]
            elif key.startswith(State.USER_PREFIX):
                user_state_delta[key.removeprefix(State.USER_PREFIX)] = state[key]
            elif not key.startswith(State.TEMP_PREFIX):
                session_state_delta[key] = state[key]
    return app_state_delta, user_state_delta, session_state_delta


def _merge_state(app_state, user_state, session_state):
    # Merge states for response
    merged_state = copy.deepcopy(session_state)
    for key in app_state.keys():
        merged_state[State.APP_PREFIX + key] = app_state[key]
    for key in user_state.keys():
        merged_state[State.USER_PREFIX + key] = user_state[key]
    return merged_state
