from pydantic import BaseModel, Field
from enum import Enum
from src.common.types import Message


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
    message: Message
    agentic: bool = Field(
        default=False, description="Whether to use agentic capabilities"
    )
    web_search: bool = Field(default=False)
