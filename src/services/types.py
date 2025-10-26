from datetime import datetime, time
from pydantic import BaseModel, Field, TypeAdapter
from typing import Literal, Annotated, Any, Dict
from uuid import uuid4

from src.common.types import (
    Message,
)


class JSONRPCMessage(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None = Field(default_factory=lambda: uuid4().hex)


class JSONRPCRequest(JSONRPCMessage):
    method: str
    params: Any | None = None


class JSONRPCError(BaseModel):
    code: int
    message: str
    data: Any | None = None


class JSONRPCResponse(JSONRPCMessage):
    result: Any | None = None
    error: JSONRPCError | None = None


class Conversation(BaseModel):
    conversation_id: str
    is_active: bool
    name: str
    summary: str | None = None
    summarized_up_to_message_order: int | None = None


class Event(BaseModel):
    id: str
    actor: str = ""
    content: Message
    timestamp: float


class Flight(BaseModel):
    origin: str
    destination: str
    departure_date: datetime
    return_date: datetime
    adults: int
    price: float
    total_duration_minutes: int
    flight_type: str
    departure_airport: str
    departure_time: datetime
    arrival_time: datetime
    legroom: Any
    extensions: list[str]
    often_delayed: bool
    plane_and_crew_by: str
    is_best: bool


class Hotel(BaseModel):
    query: str
    check_in_date: datetime
    check_out_date: datetime
    adults: int
    children: int
    geographic_location: str
    name: str
    hotel_type: str
    rate_per_night: float
    overall_rating: float
    review_count: int
    location_rating: float
    hotel_class_stars: int
    amenities: list[str]
    nearby_places: list[Dict[str, str]]
    deal: Any
    deal_description: Any
    excluded_amenities: list[str]
    essential_info: list[str]
    ratings: list[Any]
    reviews_breakdown: list[Any]
    is_best: bool
    version: int


class Activity(BaseModel):
    day: str
    time: time
    category: str
    activity: str
    detail_description: str
    duration: int
    price: float
    currency: str
    location: str
    booking_status: str
    activity_metadata: Any
    version: int


class SendMessageRequest(JSONRPCRequest):
    method: Literal["message/send"] = "message/send"
    params: Message


class ListMessageRequest(JSONRPCRequest):
    method: Literal["message/list"] = "message/list"
    # This is the conversation id
    params: str


class ListMessageResponse(JSONRPCResponse):
    result: list[Message] | None = None


class MessageInfo(BaseModel):
    message_id: str
    conversation_id: str
    context_id: str
    response: Any


class SendMessageResponse(JSONRPCResponse):
    result: Message | MessageInfo | None = None


class GetEventRequest(JSONRPCRequest):
    method: Literal["events/get"] = "events/get"


class GetEventResponse(JSONRPCResponse):
    result: list[Any] | None = None


class GetFlightsResponse(JSONRPCResponse):
    result: list[Flight] | None = None


class GetHotelsResponse(JSONRPCResponse):
    result: list[Hotel] | None = None


class GetActivitiesResponse(JSONRPCResponse):
    result: list[Activity] | None = None


class ListConversationRequest(JSONRPCRequest):
    method: Literal["conversation/list"] = "conversation/list"


class ListConversationResponse(JSONRPCResponse):
    result: list[Conversation] | None = None


class PendingMessageRequest(JSONRPCRequest):
    method: Literal["message/pending"] = "message/pending"


class PendingMessageResponse(JSONRPCResponse):
    result: list[tuple[str, str]] | None = None


class CreateConversationRequest(JSONRPCRequest):
    method: Literal["conversation/create"] = "conversation/create"
    params: str


class CreateConversationResponse(JSONRPCResponse):
    result: Conversation | None = None


class ListTaskRequest(JSONRPCRequest):
    method: Literal["task/list"] = "task/list"


class RegisterAgentRequest(JSONRPCRequest):
    method: Literal["agent/register"] = "agent/register"
    # This is the base url of the agent card
    params: str | None = None


class RegisterAgentResponse(JSONRPCResponse):
    result: str | None = None


class ListAgentRequest(JSONRPCRequest):
    method: Literal["agent/list"] = "agent/list"


class ListAgentResponse(JSONRPCResponse):
    result: list[Dict[str, Any]] | None = None


AgentRequest = TypeAdapter(
    Annotated[
        SendMessageRequest | ListConversationRequest,
        Field(discriminator="method"),
    ]
)


class AgentClientError(Exception):
    pass


class AgentClientHTTPError(AgentClientError):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"HTTP Error {status_code}: {message}")


class AgentClientJSONError(AgentClientError):
    def __init__(self, message: str):
        self.message = message
        super().__init__(f"JSON Error: {message}")
