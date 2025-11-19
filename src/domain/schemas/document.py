# src/domain/schemas/document.py
import json
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, field_validator


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
    description: str | None = None
    original_filename: str
    file_path: str
    file_size: int | None
    file_type: str
    mime_type: str | None
    status: DocumentStatusEnum
    processing_error: str | None
    created_at: datetime
    updated_at: datetime
    uploaded_by: str | None
    total_chunks: int
    processed_at: datetime | None
    doc_metadata: dict | None = None

    @field_validator(
        "doc_metadata", mode="before"
    )  # 'before' means it runs before type validation
    @classmethod
    def parse_config_data(cls, v: Any) -> dict | None:
        if v is None:
            return None  # Allow None values
        if isinstance(v, str):
            try:
                # Manually parse the JSON string
                return json.loads(v)
            except json.JSONDecodeError:
                raise ValueError("Invalid JSON string for config_data")
        return v

    is_inactive: bool | None = False

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
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
    processing_error: str | None
    processed_at: datetime | None
    total_chunks: int

    class Config:
        from_attributes = True


class DocumentUploadRequest(BaseModel):
    knowledge_base_id: uuid.UUID
    tenant_id: uuid.UUID | None = None
    doc_metadata: dict | None = None


class DocumentProcessingRequest(BaseModel):
    knowledge_base_id: uuid.UUID
    id: uuid.UUID | None = None
    file_path: str
    filename: str
    description: str | None = None
    tenant_id: uuid.UUID | None = None
    metadata: dict | None = None


class DocumentProcessingResponse(BaseModel):
    status: str
    document_id: uuid.UUID
    task_id: str

    class Config:
        from_attributes = True


# Batch operation models
class BatchDocumentItem(BaseModel):
    id: uuid.UUID | None = None
    filename: str
    file_path: str
    metadata: dict | None = None
    description: str | None = None


class BatchUploadRequest(BaseModel):
    knowledge_base_id: uuid.UUID
    tenant_id: uuid.UUID | None = None
    documents: list[BatchDocumentItem]


class BatchProcessingRequest(BaseModel):
    knowledge_base_id: uuid.UUID
    tenant_id: uuid.UUID | None = None
    documents: list[BatchDocumentItem]


class BatchOperationResult(BaseModel):
    id: uuid.UUID | None
    filename: str
    status: DocumentStatusEnum
    task_id: str | None = None
    error: str | None = None


class BatchUploadResponse(BaseModel):
    knowledge_base_id: uuid.UUID
    total_documents: int
    successful: int
    failed: int
    results: list[BatchOperationResult]


class BatchProcessingResponse(BaseModel):
    knowledge_base_id: uuid.UUID
    total_documents: int
    successful: int
    failed: int
    results: list[BatchOperationResult]


class PaginationParams(BaseModel):
    skip: int = 0
    limit: int = 10


class SearchParams(BaseModel):
    query: str | None = None
    created_by: str | None = None
