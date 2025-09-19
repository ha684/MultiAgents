from src.connector.database_conn import Base
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Index, ForeignKey
from datetime import datetime
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB, UUID
from uuid_extensions import uuid7
from zoneinfo import ZoneInfo


class ConversationModel(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    name = Column(String(255), nullable=False)
    user_id = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")),
        onupdate=lambda: datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")),
    )

    messages = relationship(
        "MessageModel", back_populates="conversation", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_app_user_conversations_opt", "user_id", "created_at"),
        Index("idx_active_conversations_opt", "is_active", "updated_at"),
        Index("idx_conversation_lookup_opt", "name", "user_id"),
    )


class MessageModel(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role = Column(String(50), nullable=False)
    parts = Column(JSONB, nullable=False)
    message_metadata = Column(JSONB)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")),
    )
    message_order = Column(Integer, nullable=False)

    conversation = relationship("ConversationModel", back_populates="messages")

    __table_args__ = (
        Index("idx_conversation_messages", "conversation_id", "message_order"),
        Index("idx_message_search", "conversation_id", "created_at"),
        Index("idx_message_time_ordered", "created_at"),
    )
