from src.connector.database_conn import Base
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Index, ForeignKey
from datetime import datetime
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
import uuid


class ConversationModel(Base):
    __tablename__ = "conversations"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid.uuid4()))
    app_name = Column(String(255), nullable=False)
    user_id = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    name = Column(String(500), default="")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    messages = relationship(
        "MessageModel", back_populates="conversation", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_app_user_conversations", "app_name", "user_id", "created_at"),
        Index("idx_active_conversations", "is_active", "updated_at"),
        Index("idx_conversation_lookup", "app_name", "user_id", "id"),
    )


class MessageModel(Base):
    __tablename__ = "messages"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid.uuid4()))
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
