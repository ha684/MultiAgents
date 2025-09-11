from src.connector.database_conn import Base
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Index, ForeignKey
from datetime import datetime
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB


class ArtifactChunkModel(Base):
    __tablename__ = "artifact_chunks"

    id = Column(String(255), primary_key=True)
    task_id = Column(String(255), nullable=False)
    index = Column(Integer, nullable=False)
    data = Column(JSONB, nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (Index("idx_artifact_task", "task_id", "index"),)


class TaskMappingModel(Base):
    __tablename__ = "task_mappings"

    message_id = Column(String(255), primary_key=True)
    task_id = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (Index("idx_task_mapping", "task_id"),)


class NextIdMappingModel(Base):
    __tablename__ = "next_id_mappings"

    last_message_id = Column(String(255), primary_key=True)
    next_message_id = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.now)


class ConversationModel(Base):
    __tablename__ = "conversations"

    id = Column(String(255), primary_key=True)
    app_name = Column(String(255), nullable=False)
    user_id = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    name = Column(String(500), default="")
    task_ids = Column(JSONB, default=list)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    messages = relationship(
        "MessageModel", back_populates="conversation", cascade="all, delete-orphan"
    )
    tasks = relationship("TaskModel", back_populates="conversation")

    __table_args__ = (
        Index("idx_app_user_conversations", "app_name", "user_id", "created_at"),
        Index("idx_active_conversations", "is_active", "updated_at"),
        Index("idx_conversation_lookup", "app_name", "user_id", "id"),
    )


class MessageModel(Base):
    __tablename__ = "messages"

    id = Column(String(255), primary_key=True)
    conversation_id = Column(
        String(255), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role = Column(String(50), nullable=False)
    parts = Column(JSONB, nullable=False)
    message_metadata = Column(JSONB)
    created_at = Column(DateTime, default=datetime.now)
    message_order = Column(Integer, nullable=False)

    conversation = relationship("ConversationModel", back_populates="messages")

    __table_args__ = (
        Index("idx_conversation_messages", "conversation_id", "message_order"),
        Index("idx_message_search", "conversation_id", "created_at"),
    )


class TaskModel(Base):
    __tablename__ = "tasks_log"

    id = Column(String(255), primary_key=True)
    conversation_id = Column(
        String(255), ForeignKey("conversations.id", ondelete="SET NULL")
    )
    status_state = Column(String(50), nullable=False)
    status_message = Column(String(500))
    task_metadata = Column(JSONB)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    status_details = relationship(
        "TaskStatusModel",
        back_populates="task",
        uselist=False,
        cascade="all, delete-orphan",
    )
    artifacts = relationship(
        "TaskArtifactModel", back_populates="task", cascade="all, delete-orphan"
    )
    history_items = relationship(
        "TaskHistoryModel", back_populates="task", cascade="all, delete-orphan"
    )
    conversation = relationship("ConversationModel", back_populates="tasks")

    __table_args__ = (
        Index("idx_conversation_tasks", "conversation_id", "created_at"),
        Index("idx_task_status_state", "status_state", "updated_at"),
    )


class TaskStatusModel(Base):
    __tablename__ = "task_status_details"

    task_id = Column(
        String(255), ForeignKey("tasks_log.id", ondelete="CASCADE"), primary_key=True
    )
    full_status = Column(JSONB, nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    task = relationship("TaskModel", back_populates="status_details")


class TaskArtifactModel(Base):
    __tablename__ = "task_artifacts"

    id = Column(String(255), primary_key=True)
    task_id = Column(
        String(255), ForeignKey("tasks_log.id", ondelete="CASCADE"), nullable=False
    )
    artifact_data = Column(JSONB, nullable=False)
    sequence_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)

    task = relationship("TaskModel", back_populates="artifacts")

    __table_args__ = (Index("idx_task_artifacts", "task_id", "sequence_order"),)


class TaskHistoryModel(Base):
    __tablename__ = "task_history"

    id = Column(String(255), primary_key=True)
    task_id = Column(
        String(255), ForeignKey("tasks_log.id", ondelete="CASCADE"), nullable=False
    )
    history_data = Column(JSONB, nullable=False)
    sequence_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)

    task = relationship("TaskModel", back_populates="history_items")

    __table_args__ = (Index("idx_task_history", "task_id", "sequence_order"),)
