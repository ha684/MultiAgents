from src.connector.database_conn import Base
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Index, ForeignKey
from datetime import datetime
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB, UUID
from uuid_extensions import uuid7


def generate_uuid7():
    """Generate time-ordered UUID v7 for better database performance"""
    return str(uuid7())


class ConversationModel(Base):
    """
    Optimized version using PostgreSQL native UUID type
    This saves storage space compared to String(36)
    """

    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    name = Column(String(255), nullable=False)
    user_id = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    name = Column(String(500), default="")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index("idx_app_user_conversations_opt", "name", "user_id", "created_at"),
        Index("idx_active_conversations_opt", "is_active", "updated_at"),
        Index("idx_conversation_lookup_opt", "name", "user_id", "id"),
    )


class MessageModel(Base):
    __tablename__ = "messages"

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    conversation_id = Column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
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
        Index("idx_message_time_ordered", "id"),
    )
