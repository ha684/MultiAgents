# src/domain/schemas/knowledge_base.py
from datetime import datetime
from typing import List, Optional
import uuid

from pydantic import BaseModel, Field


class KnowledgeBaseCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class KnowledgeBaseUpdateRequest(BaseModel):
    """Partial update request - all fields are optional"""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class KnowledgeBaseResponse(BaseModel):
    id: uuid.UUID
    name: str
    user_id: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
    is_active: bool
    document_count: Optional[int] = 0

    class Config:
        from_attributes = True


class KnowledgeBaseListResponse(BaseModel):
    items: List[KnowledgeBaseResponse]
    total: int
    skip: int
    limit: int
    has_more: bool


class KnowledgeBaseListRequest(BaseModel):
    skip: int = 0
    limit: int = 10
