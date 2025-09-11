from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
from enum import Enum


# Message Schemas
class MessageCreateRequest(BaseModel):
    content: str = Field(..., min_length=1)
    role: str = Field(default="user")


class MessageResponse(BaseModel):
    kb_id: uuid.UUID
    content: str
    role: str
    created_at: datetime
    metadata: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class MessageListResponse(BaseModel):
    items: List[MessageResponse]
    total: int
    skip: int
    limit: int
    has_more: bool


# Chat Interaction Schemas
class SearchProvider(Enum):
    """Enumeration of available search providers."""

    TAVILY = "tavily"
    FIRECRAWL = "firecrawl"


class WebSearchConfig(BaseModel):
    provider: SearchProvider = Field(default=SearchProvider.FIRECRAWL)
    active: bool = Field(default=False)
    api_key: str = ""


# Chat Interaction Schemas
class ChatRequest(BaseModel):
    messages: List[MessageCreateRequest]
    knowledge_base_id: uuid.UUID
    stream: bool = Field(default=False)
    folder_structure: Optional[Dict[str, Any]] = None
    folder_context: Optional[str] = None
    agentic: Optional[bool] = Field(
        default=False, description="Whether to use agentic capabilities"
    )
    web_search: Optional[bool] = Field(default=False)


class ChatResponse(BaseModel):
    message: MessageResponse
    sources: Optional[List[Dict[str, Any]]] = None
