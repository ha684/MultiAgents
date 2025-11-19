# src/domain/schemas/knowledge_base.py
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class KnowledgeBaseCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None


class KnowledgeBaseUpdateRequest(BaseModel):
    """Partial update request - all fields are optional"""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    is_active: bool | None = None


class KnowledgeBaseResponse(BaseModel):
    id: uuid.UUID
    name: str
    user_id: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    is_active: bool
    document_count: int | None = 0

    class Config:
        from_attributes = True


class KnowledgeBaseListResponse(BaseModel):
    items: list[KnowledgeBaseResponse]
    total: int
    skip: int
    limit: int
    has_more: bool


class KnowledgeBaseListRequest(BaseModel):
    skip: int = 0
    limit: int = 10
