# src/api/knowledge_base.py
from collections.abc import Sequence
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.documents import Document

from src.database.models.user import User
from src.dependencies.auth import get_current_user
from src.domain.schemas.knowledge_base import (
    KnowledgeBaseCreateRequest,
    KnowledgeBaseListRequest,
    KnowledgeBaseListResponse,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdateRequest,
)
from src.domain.schemas.qa import DocumentQAResponse
from src.services.knowledge_base_service import KnowledgeBaseService

router = APIRouter(
    prefix="/kb", tags=["Knowledge Base"], dependencies=[Depends(get_current_user)]
)
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
    request: KnowledgeBaseListRequest, current_user: User = Depends(get_current_user)
) -> KnowledgeBaseListResponse:
    """
    Get a list of all knowledge bases.

    Returns:
        A list of knowledge bases.
    """
    try:
        return await kb_service.list_knowledge_bases(
            skip=request.skip, limit=request.limit, user_id=current_user.id
        )
    except Exception as e:
        raise e


@router.post("/create")
async def create_knowledge_base(
    knowledge_base: KnowledgeBaseCreateRequest,
    current_user: User = Depends(get_current_user),
) -> KnowledgeBaseResponse:
    try:
        return await kb_service.create_knowledge_base(
            knowledge_base.name, knowledge_base.description, current_user.id
        )
    except Exception as e:
        raise e


@router.get("/{kb_id}")
async def get_knowledge_base_by_id(
    kb_id: str, current_user: User = Depends(get_current_user)
) -> KnowledgeBaseResponse:
    """
    Get a knowledge base by its ID.

    Args:
        kb_id: The ID of the knowledge base.
        user_id: The ID of the user.

    Returns:
        The knowledge base details.
    """
    try:
        return await kb_service.get_knowledge_base_by_id(kb_id, current_user.id)
    except Exception as e:
        raise e


@router.post("/{kb_id}/query")
async def query_knowledge_base(kb_id: str, query: str) -> list[Document]:
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
async def delete_knowledge_base(
    kb_id: str, current_user: User = Depends(get_current_user)
) -> dict:
    """
    Delete a knowledge base and all its documents.
    """
    try:
        return await kb_service.delete_knowledge_base(kb_id, current_user.id)
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


@router.patch("/{kb_id}")
async def update_knowledge_base(
    kb_id: UUID,
    knowledge_base: KnowledgeBaseUpdateRequest,
    current_user: User = Depends(get_current_user),
) -> KnowledgeBaseResponse:
    result = await kb_service.update_knowledge_base(
        kb_id=kb_id,
        name=knowledge_base.name,
        description=knowledge_base.description,
        is_active=knowledge_base.is_active,
        user_id=current_user.id,
    )

    if not result:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    return result
