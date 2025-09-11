from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import uuid
class KnowledgeBaseCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None

class KnowledgeBaseUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None

class KnowledgeBaseResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]
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
