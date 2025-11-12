# src/agents/graph/schemas.py
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class RouteDecision(BaseModel):
    """Multi-route decision output"""

    routes: List[str] = Field(description="List of subgraph names to execute, in order")


class SearchPlanSchema(BaseModel):
    """Query planner output schema"""

    queries: List[Dict[str, Any]] = Field(
        description="Essential queries that must be executed"
    )


class VerificationSchema(BaseModel):
    """Verification agent output schema"""

    is_sufficient: bool = Field(
        description="Whether the accumulated knowledge is sufficient to answer the original query"
    )
    missing_aspects: str = Field(description="Information gaps that need to be filled")


class DynamicQueriesSchema(BaseModel):
    """Dynamic query generator output schema"""

    queries: List[Dict[str, Any]] = Field(
        description="List of new targeted search queries"
    )


class ReflectionSchema(BaseModel):
    """Reflection agent output schema"""

    critique: str = Field(description="Critique of the research")
    next_steps: str = Field(description="Next steps to take")


class SqlGenerationSchema(BaseModel):
    """SQL generation output schema"""

    queries: List[Dict[str, Any]] = Field(
        description="The generated SQL SELECT queries"
    )


class SqlValidationSchema(BaseModel):
    """SQL validation output schema"""

    is_valid: bool = Field(description="Whether the SQL query is valid and safe")
    is_select_only: bool = Field(
        description="Whether the query is SELECT-only (no mutations)"
    )
    issues: List[str] = Field(
        description="List of validation issues found", default_factory=list
    )
    sanitized_query: str = Field(
        description="The sanitized/validated SQL query if valid"
    )


class SqlAnalysisSchema(BaseModel):
    """SQL analysis output schema"""

    needs_chart: bool = Field(description="Whether the query needs a chart")
    chart_type: Optional[str] = Field(description="The type of chart")
    required_queries: List[Dict[str, Any]] = Field(
        description="List of required queries"
    )


class ChartGenerationSchema(BaseModel):
    """Chart generation output schema"""

    vega_spec: str = Field(description="The generated Vega-Lite specification")
    chart_type: Literal[
        "bar",
        "line",
        "pie",
        "scatter",
        "area",
        "histogram",
        "boxplot",
        "heatmap",
        "treemap",
        "sunburst",
        "funnel",
        "gauge",
        "radial",
        "map",
    ] = Field(description="The type of chart")


class RelevanceValidationSchema(BaseModel):
    """Relevance validation output schema"""

    is_relevant: bool = Field(
        description="Whether the query is relevant to the database"
    )
    reason: str = Field(description="The reason for the relevance validation")
    suggested_rephrase: Optional[str] = Field(
        description="The suggested rephrase for the query"
    )
