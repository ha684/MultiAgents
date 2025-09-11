from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum

class RelevantFolder(BaseModel):
    relevant_folders: List[str] = Field(
        default_factory=list,
        description="List of relevant folder names identified by the agent.",
    )

class NextAction(str, Enum):
    SEARCH = "search"
    VERIFY = "verify"
    RESPOND = "respond"
    END = "end"


class SearchType(str, Enum):
    INITIAL = "initial"
    FOCUSED = "focused"
    BROADER = "broader"
    ALTERNATIVE = "alternative"


class SearchDecision(BaseModel):
    """Decision model for search routing"""
    next_action: NextAction = Field(description="The next action to take")
    reasoning: str = Field(description="Reasoning for the decision")
    search_query: Optional[str] = Field(description="Modified or new search query if needed")
    search_type: Optional[SearchType] = Field(description="Type of search to perform")


class VerificationResult(BaseModel):
    """Result of verifying search results against user query"""
    is_sufficient: bool = Field(description="Whether the search results are sufficient")
    missing_aspects: List[str] = Field(description="What aspects are missing or need deeper search")
    reasoning: str = Field(description="Reasoning for the verification result")
    suggested_searches: List[str] = Field(description="Suggested additional search queries")


class ResponseDecision(BaseModel):
    """Decision for final response generation"""
    should_respond: bool = Field(description="Whether we have enough information to respond")
    response_type: str = Field(description="Type of response: complete, partial, not_found")
    key_points: List[str] = Field(description="Key points to include in response")


class ConversationSummary(BaseModel):
    """Structured conversation summary"""
    summary: str = Field(description="Detailed summary of the conversation")
    key_topics: List[str] = Field(description="Key topics discussed")
    important_context: List[str] = Field(description="Important context that should be preserved")
    user_preferences: List[str] = Field(description="Any user preferences or requirements mentioned")