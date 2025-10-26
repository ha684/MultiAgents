# src/api/knowledge_base.py
from typing import List, Sequence
from uuid import UUID
from fastapi import APIRouter
from langchain_core.documents import Document
from src.models.knowledge_base import (
    KnowledgeBaseCreateRequest,
    KnowledgeBaseListRequest,
    KnowledgeBaseListResponse,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdateRequest,
    KnowledgeBaseDeleteRequest,
)
from src.models.qa import DocumentQAResponse
from src.services.knowledge_base_service import KnowledgeBaseService

router = APIRouter(prefix="/kb", tags=["Knowledge Base"])
kb_service = KnowledgeBaseService()


@router.get("/admin")
async def get_list_knowledge_bases_for_admin(
    limit: int = 10,
    skip: int = 0,
) -> KnowledgeBaseListResponse:
    """
    Get a list of all knowledge bases.

    Returns:
        A list of knowledge bases.
    """
    try:
        return await kb_service.list_knowledge_bases_all(skip, limit)
    except Exception as e:
        raise e


@router.post("/user")
async def get_list_knowledge_bases_for_user(
    request: KnowledgeBaseListRequest,
) -> KnowledgeBaseListResponse:
    """
    Get a list of all knowledge bases.

    Returns:
        A list of knowledge bases.
    """
    try:
        return await kb_service.list_knowledge_bases(request)
    except Exception as e:
        raise e


@router.post("/create")
async def create_knowledge_base(
    knowledge_base: KnowledgeBaseCreateRequest,
) -> KnowledgeBaseResponse:
    try:
        return await kb_service.create_knowledge_base(knowledge_base)
    except Exception as e:
        raise e


@router.get("/{kb_id}")
async def get_knowledge_base_by_id(kb_id: str, user_id: str) -> KnowledgeBaseResponse:
    """
    Get a knowledge base by its ID.

    Args:
        kb_id: The ID of the knowledge base.
        user_id: The ID of the user.

    Returns:
        The knowledge base details.
    """
    try:
        return await kb_service.get_knowledge_base_by_id(kb_id, user_id)
    except Exception as e:
        raise e


@router.post("/{kb_id}/query")
async def query_knowledge_base(kb_id: str, query: str) -> List[Document]:
    """
    Query a knowledge base by its ID.

    Args:
        kb_id: The ID of the knowledge base.
        query: The query string.
        user_id: The ID of the user.

    Returns:
        A list of documents matching the query.
    """
    try:
        return await kb_service.query_knowledge_base(kb_id, query)
    except Exception as e:
        raise e


@router.delete("/{kb_id}", response_model=dict)
async def delete_knowledge_base(request: KnowledgeBaseDeleteRequest) -> dict:
    """
    Delete a knowledge base and all its documents.

    This will:
    1. Get all documents in the knowledge base
    2. Delete all vector chunks associated with the documents
    3. Delete all documents from the database
    4. Delete the knowledge base itself

    Args:
        request: The request containing the ID of the knowledge base to delete.

    Returns:
        A success message if deletion was successful.
    """
    try:
        return await kb_service.delete_knowledge_base(request)
    except Exception as e:
        raise e


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
    try:
        return await kb_service.get_qa_pairs_by_kb_id(kb_id, limit)
    except Exception as e:
        raise e


@router.put("/{kb_id}/update")
async def update_knowledge_base(
    knowledge_base: KnowledgeBaseUpdateRequest,
) -> KnowledgeBaseResponse:
    """
    Update a knowledge base.

    Args:
        knowledge_base: The knowledge base to update.

    Returns:
        The updated knowledge base.
    """
    try:
        return await kb_service.update_knowledge_base(knowledge_base)
    except Exception as e:
        raise e
