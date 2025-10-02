# src/agents/graph/schemas.py
from pydantic import BaseModel, Field
from typing import List, Literal, Dict, Any


class RouteDecision(BaseModel):
    """Router output schema"""

    route: Literal["chitchat", "simple_search", "deep_research"] = Field(
        description="The route to take based on query complexity"
    )


class SearchPlanSchema(BaseModel):
    """Query planner output schema"""

    core_queries: List[Dict[str, Any]] = Field(
        description="Essential queries that must be executed"
    )
    optional_queries: List[Dict[str, Any]] = Field(
        description="Additional queries for comprehensive coverage"
    )
    max_searches: int = Field(
        description="Maximum number of search iterations", ge=3, le=10
    )


class VerificationSchema(BaseModel):
    """Verification agent output schema"""

    sufficient: bool = Field(description="Whether accumulated knowledge is sufficient")
    confidence: float = Field(description="Confidence score 0-1", ge=0.0, le=1.0)
    next_action: Literal["continue_planned", "generate_dynamic", "synthesize"] = Field(
        description="Next action to take"
    )
    missing_aspects: List[str] = Field(
        description="List of information gaps that need to be filled"
    )
    reasoning: str = Field(description="Detailed reasoning for the decision")


class DynamicQueriesSchema(BaseModel):
    """Dynamic query generator output schema"""

    queries: List[Dict[str, Any]] = Field(
        description="List of new targeted search queries"
    )
