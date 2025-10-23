# src/agents/graph/schemas.py
from typing import Any, Dict, List, Literal, Optional
from enum import Enum
from pydantic import BaseModel, Field


class RouteDecision(BaseModel):
    """Router output schema"""

    route: str = Field(description="The route to take based on query complexity")


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
    confidence: Literal["high", "medium", "low"] = Field(
        description="Confidence level in the sufficiency assessment"
    )
    missing_aspects: List[str] = Field(
        description="List of information gaps that need to be filled"
    )


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


class ResponseMode(str, Enum):
    """Modes for response_agent to handle different scenarios"""

    ADVANCE = "advance"
    STANDARD = "standard"
    CHITCHAT = "chitchat"
    FOLLOWUP = "followup"
    NO_VIABLE_OPTION = "no_viable_option"
    ERROR = "error"
    CONFIRMATION_REQUIRED = "confirmation_required"
    SQL_RESPONSE = "sql_response"


# class Event(LlmResponse):
#   """Represents an event in a conversation between agents and users.

#   It is used to store the content of the conversation, as well as the actions
#   taken by the agents like function calls, etc.

#   Attributes:
#     invocation_id: Required. The invocation ID of the event. Should be non-empty
#       before appending to a session.
#     author: Required. "user" or the name of the agent, indicating who appended
#       the event to the session.
#     actions: The actions taken by the agent.
#     long_running_tool_ids: The ids of the long running function calls.
#     branch: The branch of the event.
#     id: The unique identifier of the event.
#     timestamp: The timestamp of the event.
#     get_function_calls: Returns the function calls in the event.
#   """

#   model_config = ConfigDict(
#       extra='forbid',
#       ser_json_bytes='base64',
#       val_json_bytes='base64',
#       alias_generator=alias_generators.to_camel,
#       populate_by_name=True,
#   )
#   """The pydantic model config."""

#   invocation_id: str = ''
#   """The invocation ID of the event. Should be non-empty before appending to a session."""
#   author: str
#   """'user' or the name of the agent, indicating who appended the event to the
#   session."""
#   actions: EventActions = Field(default_factory=EventActions)
#   """The actions taken by the agent."""

#   long_running_tool_ids: Optional[set[str]] = None
#   """Set of ids of the long running function calls.
#   Agent client will know from this field about which function call is long running.
#   only valid for function call event
#   """
#   branch: Optional[str] = None
#   """The branch of the event.

#   The format is like agent_1.agent_2.agent_3, where agent_1 is the parent of
#   agent_2, and agent_2 is the parent of agent_3.

#   Branch is used when multiple sub-agent shouldn't see their peer agents'
#   conversation history.
#   """

#   # The following are computed fields.
#   # Do not assign the ID. It will be assigned by the session.
#   id: str = ''
#   """The unique identifier of the event."""
#   timestamp: float = Field(default_factory=lambda: datetime.now().timestamp())
#   """The timestamp of the event."""

#   def model_post_init(self, __context):
#     """Post initialization logic for the event."""
#     # Generates a random ID for the event.
#     if not self.id:
#       self.id = Event.new_id()

#   def is_final_response(self) -> bool:
#     """Returns whether the event is the final response of an agent.

#     NOTE: This method is ONLY for use by Agent Development Kit.

#     Note that when multiple agents participage in one invocation, there could be
#     one event has `is_final_response()` as True for each participating agent.
#     """
#     if self.actions.skip_summarization or self.long_running_tool_ids:
#       return True
#     return (
#         not self.get_function_calls()
#         and not self.get_function_responses()
#         and not self.partial
#         and not self.has_trailing_code_execution_result()
#     )

#   def get_function_calls(self) -> list[types.FunctionCall]:
#     """Returns the function calls in the event."""
#     func_calls = []
#     if self.content and self.content.parts:
#       for part in self.content.parts:
#         if part.function_call:
#           func_calls.append(part.function_call)
#     return func_calls

#   def get_function_responses(self) -> list[types.FunctionResponse]:
#     """Returns the function responses in the event."""
#     func_response = []
#     if self.content and self.content.parts:
#       for part in self.content.parts:
#         if part.function_response:
#           func_response.append(part.function_response)
#     return func_response

#   def has_trailing_code_execution_result(
#       self,
#   ) -> bool:
#     """Returns whether the event has a trailing code execution result."""
#     if self.content:
#       if self.content.parts:
#         return self.content.parts[-1].code_execution_result is not None
#     return False

#   @staticmethod
#   def new_id():
#     return str(uuid.uuid4())
