# src/domain/schemas/chat.py
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal, Self

from langchain_core.documents import Document
from pydantic import BaseModel, Field, field_serializer, model_validator
from uuid_extensions import uuid7


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
    retrieval_context: RetrievalContext | None = None


class RetrievalContext(BaseModel):
    """Save all context retrieved for a message"""

    total_retrieved: int
    total_cited: int
    cited_chunks: list[Document]
    model_config = {"arbitrary_types_allowed": True}

    @field_serializer("cited_chunks")
    def serialize_documents(self, documents: list[Document]) -> list[dict]:
        """Serialize LangChain Document objects to dicts"""
        return [
            {"page_content": doc.page_content, "metadata": doc.metadata}
            for doc in documents
        ]


class SearchProvider(Enum):
    """Enumeration of available search providers."""

    TAVILY = "tavily"
    FIRECRAWL = "firecrawl"


class WebSearchConfig(BaseModel):
    provider: SearchProvider = Field(default=SearchProvider.FIRECRAWL)
    active: bool = Field(default=False)
    api_key: str = ""

    @field_serializer("provider")
    def serialize_provider(self, provider: SearchProvider) -> str:
        return provider.value


class ChatRequest(BaseModel):
    message: Message
    agentic: bool = Field(
        default=False, description="Whether to use agentic capabilities"
    )
    web_search: bool = Field(default=False)


class HealthCheckResponse(BaseModel):
    status: str
    timestamp: datetime


class Citation(BaseModel):
    source_id: int = Field(
        ...,
        description="The integer ID of a SPECIFIC source which justifies the answer.",
    )
    quote: str = Field(
        ...,
        description="The VERBATIM quote from the specified source that justifies the answer.",
    )


class SupportCitation(BaseModel):
    support_citation: list[Citation] = Field(
        ...,
        description="A list of citations that support the answer to the query.",
    )


class CitationIndexes(BaseModel):
    indexes: list[int | str]


class Reference(BaseModel):
    id: str = Field(
        ...,
        description="The integer ID of the chunk.",
    )
    source_id: str = Field(
        ...,
        description="The integer ID of the document.",
    )
    source_index: int = Field(
        ...,
        description="The index of the source in the list of sources.",
    )
    source: str = Field(
        ...,
        description="The name of the source.",
    )
    page_content: str = Field(
        ...,
        description="The content of the source, which may include text, images, or other media.",
    )
    start_index: int = Field(
        ...,
        description="The start index of the source in the document.",
    )
    end_index: int = Field(
        ...,
        description="The end index of the source in the document.",
    )
    llm_received_index: int = Field(
        ...,
        description="The index of the source in the list of sources received from the LLM.",
    )


class Conversation(BaseModel):
    conversation_id: str
    is_active: bool
    name: str
    summary: str | None = None
    summarized_up_to_message_order: int | None = None
