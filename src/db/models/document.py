from src.connector.database_conn import Base
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey
from datetime import datetime
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from typing import List, Optional
from sqlalchemy import func, Text
import uuid


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    user_id: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    documents: Mapped[List["Document"]] = relationship(
        "Document", back_populates="knowledge_base", cascade="all, delete-orphan"
    )

    qa_pairs: Mapped[List["DocumentQA"]] = relationship(
        "DocumentQA", back_populates="knowledge_base", cascade="all, delete-orphan"
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_bases.id"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)  # Path in MinIO
    file_size: Mapped[Optional[int]] = mapped_column(Integer)  # File size in bytes
    file_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # pdf, docx, txt, etc.
    mime_type: Mapped[Optional[str]] = mapped_column(String(100))
    doc_metadata: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    is_inactive: Mapped[Optional[bool]] = mapped_column(
        Boolean, default=False
    )  # Flag to indicate if the document is deactivated

    # Processing status
    status: Mapped[str] = mapped_column(
        String(50), default="pending"
    )  # uploaded, processing, processed, failed
    processing_error: Mapped[Optional[str]] = mapped_column(
        Text
    )  # Error message if processing failed

    # Document metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    uploaded_by: Mapped[Optional[str]] = mapped_column(
        String(255)
    )  # User ID or username who uploaded the document

    # Processing metadata
    total_chunks: Mapped[int] = mapped_column(
        Integer, default=0
    )  # Number of chunks created from this document
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    knowledge_base: Mapped["KnowledgeBase"] = relationship(
        "KnowledgeBase", back_populates="documents"
    )

    qa_pairs: Mapped[List["DocumentQA"]] = relationship(
        "DocumentQA", back_populates="document", cascade="all, delete-orphan"
    )


class DocumentQA(Base):
    __tablename__ = "document_qa"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False
    )
    kb_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_bases.id"), nullable=False
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    document: Mapped["Document"] = relationship("Document", back_populates="qa_pairs")
    knowledge_base: Mapped["KnowledgeBase"] = relationship(
        "KnowledgeBase", back_populates="qa_pairs"
    )
