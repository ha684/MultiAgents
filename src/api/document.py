# src/api/document.py
from typing import List, Optional, Sequence, Dict, Any
import uuid

from fastapi import APIRouter, UploadFile, File, Request, HTTPException

from src.domain.schemas.document import (
    DocumentResponse,
    DocumentStatusEnum,
    DocumentUploadResponse,
    DocumentListResponse,
    DocumentProcessingStatusResponse,
    PaginationParams,
    SearchParams,
)
from src.domain.schemas.qa import DocumentQAResponse
from src.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["Document"])
document_service = DocumentService()


@router.post("/upload_and_process", response_model=DocumentUploadResponse)
async def upload_document(
    request: Request,
    knowledge_base_id: uuid.UUID,
    tenant_id: Optional[str] = None,
    file: UploadFile = File(...),
    metadata: Optional[Dict[str, Any]] = None,
) -> DocumentUploadResponse:
    """
    Upload a document to a knowledge base.
    """
    MAX_FILE_SIZE = 100 * 1024 * 1024

    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size allowed is {MAX_FILE_SIZE // (1024 * 1024)}MB",
        )

    try:
        document, task_id = await document_service.upload_and_process_document(
            knowledge_base_id=knowledge_base_id,
            file=file,
            tenant_id=tenant_id,
            metadata=metadata,
        )

        return DocumentUploadResponse(
            id=document.id,
            filename=document.filename,
            original_filename=document.original_filename,
            status=DocumentStatusEnum.PENDING,
            task_id=task_id,
        )

    except Exception as e:
        raise e


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: uuid.UUID) -> DocumentResponse:
    """
    Get document details.
    """
    try:
        return await document_service.get_document(document_id)
    except Exception as e:
        raise e


@router.get("/documents/{document_id}/content")
async def get_document_content(document_id: uuid.UUID) -> Dict[str, Any]:
    """
    Get full text content of a processed document.
    Only available after document processing is complete.
    """
    try:
        document = await document_service.get_document(document_id)

        if document.status != DocumentStatusEnum.FINISHED:
            raise HTTPException(
                status_code=400,
                detail=f"Document is not ready. Current status: {document.status}",
            )

        if not document.full_text_content:
            raise HTTPException(
                status_code=404, detail="Document content not available"
            )

        return {
            "document_id": str(document.id),
            "filename": document.filename,
            "content": document.full_text_content,
            "processed_at": document.processed_at,
        }
    except Exception as e:
        raise e


@router.get("/{document_id}/status", response_model=DocumentProcessingStatusResponse)
async def get_document_status(
    document_id: uuid.UUID,
) -> DocumentProcessingStatusResponse:
    """
    Get document processing status.
    """
    try:
        return await document_service.get_document_status(document_id)
    except Exception as e:
        raise e


@router.post("/status")
async def get_document_status_by_ids(
    document_ids: list[uuid.UUID],
) -> List[DocumentProcessingStatusResponse]:
    """
    Get processing status for multiple documents.
    """
    try:
        return await document_service.get_multiple_document_status(document_ids)
    except Exception as e:
        raise e


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    knowledge_base_id: uuid.UUID,
    skip: int = 0,
    limit: int = 10,
    query: Optional[str] = None,
    created_by: Optional[str] = None,
) -> DocumentListResponse:
    """
    List documents in a knowledge base.
    """

    pagination = PaginationParams(skip=skip, limit=limit)
    search = None
    if query or created_by is not None:
        search = SearchParams(query=query, created_by=created_by)

    try:
        return await document_service.list_documents(
            knowledge_base_id, pagination, search
        )
    except Exception as e:
        raise e


@router.delete("/{document_id}", response_model=dict)
async def delete_document(document_id: uuid.UUID) -> dict:
    """
    Delete a document.
    """
    try:
        await document_service.delete_document(document_id)
        return {"detail": "Document deleted successfully"}
    except Exception as e:
        raise e


@router.patch("/{document_id}/active", response_model=DocumentResponse)
async def toggle_document_active(
    document_id: uuid.UUID, active: bool
) -> DocumentResponse:
    """
    Activate or deactivate a document.
    """
    try:
        return await document_service.toggle_document_active(document_id, active)
    except Exception as e:
        raise e


@router.get("/{document_id}/qa")
async def get_qa_pairs(document_id: uuid.UUID) -> Sequence[DocumentQAResponse]:
    """
    Get question-answer pairs for a document.
    """
    try:
        return await document_service.get_document_qa_pairs(document_id)
    except Exception as e:
        raise e


@router.post("/{document_id}/related")
async def get_related_documents(
    document_id: str, kb_id: str, config: Optional[Dict] = None
) -> Dict:
    """
    Get related documents for a document.
    """
    default_config = {
        "score_threshold": 0.0,
        "embed_top": 50,
        "rerank_top": 0,
    }

    if config:
        default_config.update(config)

    try:
        related_docs = await document_service.get_related_document_ids(
            document_id=document_id, kb_id=kb_id, **default_config
        )

        return {
            "source_document_id": document_id,
            "related_documents": related_docs,
            "total_found": len(related_docs),
        }

    except Exception as e:
        raise e
