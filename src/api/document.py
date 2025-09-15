# src/api/document.py
from fastapi import APIRouter, HTTPException, UploadFile, File
from typing import List, Optional, Sequence, Dict, Any
import uuid
from src.models.document import (
    DocumentResponse,
    DocumentStatusEnum,
    DocumentUploadResponse,
    DocumentListResponse,
    DocumentProcessingStatusResponse,
    BatchUploadResponse,
)
from src.models.common import PaginationParams, SearchParams
from src.models.qa import DocumentQAResponse
from src.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["Document"])
document_service = DocumentService()


@router.post("/upload_and_process", response_model=DocumentUploadResponse)
async def upload_document(
    knowledge_base_id: uuid.UUID,
    tenant_id: Optional[str] = None,
    file: UploadFile = File(...),
    metadata: Optional[Dict[str, Any]] = None,
) -> DocumentUploadResponse:
    """
    Upload a document to a knowledge base.
    """

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
        raise HTTPException(
            status_code=500, detail=f"Failed to upload document: {str(e)}"
        )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: uuid.UUID) -> DocumentResponse:
    """
    Get document details.
    """
    try:
        return await document_service.get_document(document_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get document: {str(e)}")


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
        raise HTTPException(
            status_code=500, detail=f"Failed to get document status: {str(e)}"
        )


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
        raise HTTPException(
            status_code=500, detail=f"Failed to get multiple document status: {str(e)}"
        )


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
        raise HTTPException(
            status_code=500, detail=f"Failed to list documents: {str(e)}"
        )


@router.delete("/{document_id}", response_model=dict)
async def delete_document(document_id: uuid.UUID) -> dict:
    """
    Delete a document.
    """
    try:
        await document_service.delete_document(document_id)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to delete document: {str(e)}"
        )
    return {"detail": "Document deleted successfully"}


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
        raise HTTPException(
            status_code=500, detail=f"Failed to toggle document active: {str(e)}"
        )


@router.post("/batch/upload_and_process", response_model=BatchUploadResponse)
async def batch_upload_and_process(
    knowledge_base_id: uuid.UUID,
    tenant_id: Optional[str] = None,
    files: List[UploadFile] = File(...),
) -> BatchUploadResponse:
    """
    Upload and process multiple documents to a knowledge base in a single request.
    """

    try:
        successful, failed, results = await document_service.batch_upload_and_process(
            knowledge_base_id=knowledge_base_id, files=files, tenant_id=tenant_id
        )

        return BatchUploadResponse(
            knowledge_base_id=knowledge_base_id,
            total_documents=len(files),
            successful=successful,
            failed=failed,
            results=results,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to process batch upload: {str(e)}"
        )


@router.get("/{document_id}/qa")
async def get_qa_pairs(document_id: uuid.UUID) -> Sequence[DocumentQAResponse]:
    """
    Get question-answer pairs for a document.
    """
    try:
        return await document_service.get_document_qa_pairs(document_id)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get document QA pairs: {str(e)}"
        )


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
        raise HTTPException(
            status_code=500, detail=f"Failed to find related documents: {str(e)}"
        )
