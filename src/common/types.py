# src/common/types.py
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Self, Optional, List
from zoneinfo import ZoneInfo

from pydantic import (
    BaseModel,
    Field,
    model_validator,
    field_serializer,
)
from uuid_extensions import uuid7
from langchain_core.documents import Document


class TextPart(BaseModel):
    type: Literal["text"] = "text"
    text: str
    metadata: dict[str, Any] | None = None


class FileContent(BaseModel):
    name: str | None = None
    mimeType: str | None = None
    bytes: str | None = None
    uri: str | None = None

    @model_validator(mode="after")
    def check_content(self) -> Self:
        if not (self.bytes or self.uri):
            raise ValueError("Either 'bytes' or 'uri' must be present in the file data")
        if self.bytes and self.uri:
            raise ValueError(
                "Only one of 'bytes' or 'uri' can be present in the file data"
            )
        return self


class FilePart(BaseModel):
    type: Literal["file"] = "file"
    file: FileContent
    metadata: dict[str, Any] | None = None


class DataPart(BaseModel):
    type: Literal["data"] = "data"
    data: dict[str, Any]
    metadata: dict[str, Any] | None = None


Part = Annotated[TextPart | FilePart | DataPart, Field(discriminator="type")]


class Message(BaseModel):
    id: str = Field(default_factory=lambda: uuid7().hex)
    role: Literal["user", "agent"]
    parts: list[Part]
    metadata: dict[str, Any] | None = None
    retrieval_context: Optional[RetrievalContext] = None


class HealthCheckResponse(BaseModel):
    status: str
    timestamp: datetime


class RetrievalContext(BaseModel):
    """Save all context retrieved for a message"""

    original_query: str
    contextualized_query: str
    retrieved_at: datetime = Field(
        default_factory=lambda: datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    )
    total_retrieved: int
    total_cited: int
    cited_chunks: List[Document]
    search_method: Literal["rag", "web"]
    model_config = {"arbitrary_types_allowed": True}

    @field_serializer("cited_chunks")
    def serialize_documents(self, documents: List[Document]) -> List[dict]:
        """Serialize LangChain Document objects to dicts"""
        return [
            {"page_content": doc.page_content, "metadata": doc.metadata}
            for doc in documents
        ]

    @field_serializer("retrieved_at")
    def serialize_datetime(self, dt: datetime) -> str:
        """Serialize datetime to ISO format string"""
        return dt.isoformat()
