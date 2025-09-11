from enum import Enum
import json
from pydantic import BaseModel, field_validator
from typing import Any, Optional, List
from datetime import datetime
import uuid


class DocumentStatusEnum(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    FINISHED = "finished"
    FAILED = "failed"
    TIMEOUT = "timeout"

    def __str__(self) -> str:
        return self.value


class DocumentResponse(BaseModel):
    id: uuid.UUID
    knowledge_base_id: uuid.UUID
    filename: str
    description: Optional[str] = None
    original_filename: str
    file_path: str
    file_size: Optional[int]
    file_type: str
    mime_type: Optional[str]
    status: DocumentStatusEnum
    processing_error: Optional[str]
    created_at: datetime
    updated_at: datetime
    uploaded_by: Optional[str]
    total_chunks: int
    processed_at: Optional[datetime]
    doc_metadata: Optional[dict] = None

    @field_validator(
        "doc_metadata", mode="before"
    )  # 'before' means it runs before type validation
    @classmethod
    def parse_config_data(cls, v: Any) -> Optional[dict]:
        if v is None:
            return None  # Allow None values
        if isinstance(v, str):
            try:
                # Manually parse the JSON string
                return json.loads(v)
            except json.JSONDecodeError:
                raise ValueError("Invalid JSON string for config_data")
        return v

    is_inactive: Optional[bool] = False

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    items: List[DocumentResponse]
    total: int
    skip: int
    limit: int
    has_more: bool


class DocumentUploadResponse(BaseModel):
    id: uuid.UUID
    filename: str
    original_filename: str
    status: DocumentStatusEnum
    task_id: str

    class Config:
        from_attributes = True


class DocumentProcessingStatusResponse(BaseModel):
    id: uuid.UUID
    filename: str
    original_filename: str
    status: DocumentStatusEnum
    processing_error: Optional[str]
    processed_at: Optional[datetime]
    total_chunks: int

    class Config:
        from_attributes = True


class DocumentUploadRequest(BaseModel):
    knowledge_base_id: uuid.UUID
    tenant_id: Optional[uuid.UUID] = None
    doc_metadata: Optional[dict] = None


class DocumentProcessingRequest(BaseModel):
    knowledge_base_id: uuid.UUID
    id: Optional[uuid.UUID] = None
    file_path: str
    filename: str
    description: Optional[str] = None
    tenant_id: Optional[uuid.UUID] = None
    metadata: Optional[dict] = None


class DocumentProcessingResponse(BaseModel):
    status: str
    document_id: uuid.UUID
    task_id: str

    class Config:
        from_attributes = True


# Batch operation models
class BatchDocumentItem(BaseModel):
    id: Optional[uuid.UUID] = None
    filename: str
    file_path: str
    metadata: Optional[dict] = None
    description: Optional[str] = None


class BatchUploadRequest(BaseModel):
    knowledge_base_id: uuid.UUID
    tenant_id: Optional[uuid.UUID] = None
    documents: List[BatchDocumentItem]


class BatchProcessingRequest(BaseModel):
    knowledge_base_id: uuid.UUID
    tenant_id: Optional[uuid.UUID] = None
    documents: List[BatchDocumentItem]


class BatchOperationResult(BaseModel):
    id: Optional[uuid.UUID]
    filename: str
    status: DocumentStatusEnum
    task_id: Optional[str] = None
    error: Optional[str] = None


class BatchUploadResponse(BaseModel):
    knowledge_base_id: uuid.UUID
    total_documents: int
    successful: int
    failed: int
    results: List[BatchOperationResult]


class BatchProcessingResponse(BaseModel):
    knowledge_base_id: uuid.UUID
    total_documents: int
    successful: int
    failed: int
    results: List[BatchOperationResult]
