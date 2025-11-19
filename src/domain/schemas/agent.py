# src/domain/schemas/agent.py

from enum import Enum

from pydantic import BaseModel, Field


class RelevantFolder(BaseModel):
    relevant_folders: list[str] = Field(
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
    search_query: str | None = Field(
        description="Modified or new search query if needed"
    )
    search_type: SearchType | None = Field(description="Type of search to perform")


class VerificationResult(BaseModel):
    """Result of verifying search results against user query"""

    is_sufficient: bool = Field(description="Whether the search results are sufficient")
    missing_aspects: list[str] = Field(
        description="What aspects are missing or need deeper search"
    )
    reasoning: str = Field(description="Reasoning for the verification result")
    suggested_searches: list[str] = Field(
        description="Suggested additional search queries"
    )


class ResponseDecision(BaseModel):
    """Decision for final response generation"""

    should_respond: bool = Field(
        description="Whether we have enough information to respond"
    )
    response_type: str = Field(
        description="Type of response: complete, partial, not_found"
    )
    key_points: list[str] = Field(description="Key points to include in response")


class ConversationSummary(BaseModel):
    """Structured conversation summary"""

    summary: str = Field(description="Detailed summary of the conversation")
    key_topics: list[str] = Field(description="Key topics discussed")
    important_context: list[str] = Field(
        description="Important context that should be preserved"
    )
    user_preferences: list[str] = Field(
        description="Any user preferences or requirements mentioned"
    )
