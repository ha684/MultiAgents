from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime
import uuid


# Common API Schemas
class PaginationParams(BaseModel):
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=1000)


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SuccessResponse(BaseModel):
    message: str
    data: Optional[Any] = None


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    services: dict = Field(default_factory=dict)


# Search and Filter Schemas
class SearchParams(BaseModel):
    query: Optional[str] = Field(None, min_length=1)
    created_by: Optional[str] = None
    is_active: Optional[bool] = True


class DateRangeFilter(BaseModel):
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class BulkDeleteRequest(BaseModel):
    ids: List[uuid.UUID]


class BulkOperationResponse(BaseModel):
    success_count: int
    failure_count: int
    errors: Optional[List[dict]] = None
