from typing import List, Sequence
from uuid import UUID
from fastapi import APIRouter
from langchain_core.documents import Document
from src.models.common import PaginationParams
from src.models.knowledge_base import (
    KnowledgeBaseCreateRequest,
    KnowledgeBaseListResponse,
    KnowledgeBaseResponse,
)
from src.models.qa import DocumentQAResponse
from src.services.knowledge_base_service import KnowledgeBaseService

router = APIRouter(prefix="/kb", tags=["Knowledge Base"])
kb_service = KnowledgeBaseService()

@router.get("/")
async def get_list_knowledge_bases(
    skip: int = 0, limit: int = 10
) -> KnowledgeBaseListResponse:
    """
    Get a list of all knowledge bases.

    Returns:
        A list of knowledge bases.
    """
    pagination = PaginationParams(skip=skip, limit=limit)
    return await kb_service.list_knowledge_bases(pagination)

@router.post("/")
async def create_knowledge_base(
    knowledge_base: KnowledgeBaseCreateRequest
) -> KnowledgeBaseResponse:
    return await kb_service.create_knowledge_base(knowledge_base)

@router.get("/{kb_id}")
async def get_knowledge_base_by_id(
    kb_id: str
) -> KnowledgeBaseResponse:
    """
    Get a knowledge base by its ID.

    Args:
        kb_id: The ID of the knowledge base.

    Returns:
        The knowledge base details.
    """
    return await kb_service.get_knowledge_base_by_id(kb_id)

@router.post("/{kb_id}/query")
async def query_knowledge_base(
    kb_id: str, query: str
) -> List[Document]:
    """
    Query a knowledge base by its ID.

    Args:
        kb_id: The ID of the knowledge base.
        query: The query string.

    Returns:
        A list of documents matching the query.
    """
    return await kb_service.query_knowledge_base(kb_id, query)

@router.delete("/{kb_id}", response_model=dict)
async def delete_knowledge_base(kb_id: str) -> dict:
    """
    Delete a knowledge base and all its documents.

    This will:
    1. Get all documents in the knowledge base
    2. Delete all vector chunks associated with the documents
    3. Delete all documents from the database
    4. Delete the knowledge base itself

    Args:
        kb_id: The ID of the knowledge base to delete.

    Returns:
        A success message if deletion was successful.
    """
    return await kb_service.delete_knowledge_base(kb_id)


@router.get("/{kb_id}/qa")
async def get_qa_pairs_by_kb_id(
    kb_id: UUID, limit: int = 25
) -> Sequence[DocumentQAResponse]:
    """
    Get all question-answer pairs for a knowledge base.

    Args:
        kb_id: The ID of the knowledge base.

    Returns:
        A list of question-answer pairs.
    """
    return await kb_service.get_qa_pairs_by_kb_id(kb_id, limit)
