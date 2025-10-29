# src/services/knowledge_base_service.py
from typing import List, Sequence
from uuid import UUID

from fastapi import HTTPException
from langchain_core.documents import Document

from src.database import document_repository, knowledge_base_repository, qa_repository
from src.domain.schemas.knowledge_base import (
    KnowledgeBaseCreateRequest,
    KnowledgeBaseDeleteRequest,
    KnowledgeBaseListRequest,
    KnowledgeBaseListResponse,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdateRequest,
)
from src.domain.schemas.qa import DocumentQAResponse
from src.rag.vectorstores import vector_retrieval, vector_storage
from src.utils.decorators import singleton
from src.utils.logger_conf import logger
from src.utils.reference import normalize_ref


@singleton
class KnowledgeBaseService:
    def __init__(self):
        self.kb_repository = knowledge_base_repository
        self.document_repository = document_repository
        self.qa_repository = qa_repository

    async def list_knowledge_bases(
        self, request: KnowledgeBaseListRequest
    ) -> KnowledgeBaseListResponse:
        """Get a list of all knowledge bases."""
        logger.info("Fetching list of all knowledge bases")
        return await self.kb_repository.list(request)

    async def list_knowledge_bases_all(
        self, skip: int, limit: int
    ) -> KnowledgeBaseListResponse:
        """Get a list of all knowledge bases."""
        logger.info("Fetching list of all knowledge bases")
        return await self.kb_repository.list_all(skip, limit)

    async def create_knowledge_base(self, knowledge_base: KnowledgeBaseCreateRequest):
        """Create a new knowledge base."""
        logger.info(f"Creating knowledge base: {knowledge_base.name}")
        return await self.kb_repository.create(knowledge_base)

    async def get_knowledge_base_by_id(
        self, kb_id: str, user_id: str
    ) -> KnowledgeBaseResponse:
        """Get a knowledge base by its ID."""
        logger.info(f"Fetching knowledge base with ID: {kb_id}")
        kb = await self.kb_repository.get(kb_id, user_id)
        if not kb:
            raise HTTPException(status_code=404, detail="Knowledge base not found")
        return kb

    async def query_knowledge_base(self, kb_id: str, query: str) -> List[Document]:
        """Query a knowledge base by its ID."""
        logger.info(f"Querying knowledge base {kb_id} with query: {query}")

        documents = await vector_retrieval.retrieve(
            kb_id=str(kb_id), query=query, filters=None, top_n=20, top_k=50
        )
        if not documents:
            logger.warning(f"No documents found for query: {query} in KB {kb_id}")
            return []

        documents = normalize_ref(documents, normalize_images=False)

        return documents

    async def delete_knowledge_base(self, request: KnowledgeBaseDeleteRequest) -> dict:
        """Delete a knowledge base and all its documents."""
        kb = await self.kb_repository.get(kb_id=request.id, user_id=request.user_id)
        if not kb:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

        logger.info(f"Deleting knowledge base {request.id} and all its documents")

        try:
            total = await self.document_repository.count_documents_in_kb(kb.id)
            await self.kb_repository.delete(kb.id)
            await vector_storage.delete_chunks_by_kb_id(request.id)

            logger.info(
                f"Successfully deleted knowledge base {request.id} with {total} documents files"
            )
            return {
                "detail": f"Knowledge base deleted successfully. Removed {total} documents files."
            }
        except Exception as e:
            logger.exception(
                f"Unexpected error deleting knowledge base {request.id}: {str(e)}"
            )
            raise HTTPException(
                status_code=500, detail="Failed to delete knowledge base"
            )

    async def get_qa_pairs_by_kb_id(
        self, kb_id: UUID, limit: int = 25
    ) -> Sequence[DocumentQAResponse]:
        """Get all question-answer pairs for a knowledge base."""
        logger.info(f"Fetching QA pairs for knowledge base {kb_id}")

        qas = await self.qa_repository.get_random_qa_by_kb_id(kb_id, limit)

        if not qas:
            logger.info(f"No QA pairs found for knowledge base {kb_id}")
            return []

        return qas

    async def update_knowledge_base(
        self, knowledge_base_update_request: KnowledgeBaseUpdateRequest
    ):
        """Update a knowledge base."""
        return await self.kb_repository.update(knowledge_base_update_request)
