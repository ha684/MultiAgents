import uuid
from typing import List, Optional
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from src.db.models.document import Document, KnowledgeBase
from src.db.repository.database_session import DatabaseSession
from src.models.knowledge_base import (
    KnowledgeBaseCreateRequest,
    KnowledgeBaseListRequest,
    KnowledgeBaseListResponse,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdateRequest,
)
from src.utils.logger_conf import logger
from src.utils.decorators import singleton


@singleton
class KnowledgeBaseRepository:
    """Service layer for Knowledge Base operations"""

    async def create(
        self,
        request: KnowledgeBaseCreateRequest,
    ) -> KnowledgeBaseResponse:
        """Create a new knowledge base"""
        try:
            async with DatabaseSession() as session:
                kb = KnowledgeBase(
                    name=request.name,
                    description=request.description,
                    user_id=request.user_id,
                )
                session.add(kb)
                await session.flush()
                await session.refresh(kb)
            return KnowledgeBaseResponse.model_validate(kb)
        except SQLAlchemyError as e:
            logger.error(f"Error creating knowledge base: {e.args[0]}")
            raise e

    async def get(self, kb_id: uuid.UUID) -> Optional[KnowledgeBase]:
        """Get a knowledge base by ID"""
        try:
            async with DatabaseSession() as session:
                stmt = select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
                result = await session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"Error getting knowledge base: {e.args[0]}")
            raise e

    async def count_documents(self, kb_id: uuid.UUID) -> int:
        """Count documents in a knowledge base"""
        try:
            async with DatabaseSession() as session:
                stmt = select(func.count(Document.id)).where(
                    Document.knowledge_base_id == kb_id
                )
                result = await session.execute(stmt)
            return result.scalar_one_or_none() or 0
        except SQLAlchemyError as e:
            logger.error(f"Error counting documents: {e.args[0]}")
            raise e

    async def update(
        self, request: KnowledgeBaseUpdateRequest
    ) -> Optional[KnowledgeBaseResponse]:
        """Update a knowledge base"""
        try:
            async with DatabaseSession() as session:
                stmt = select(KnowledgeBase).where(KnowledgeBase.id == request.id)
                result = await session.execute(stmt)
                kb = result.scalar_one_or_none()

                if not kb:
                    return None

                update_data = request.model_dump(exclude_unset=True)

                if "name" in update_data:
                    kb.name = update_data["name"]
                if "description" in update_data:
                    kb.description = update_data["description"]
                if "is_active" in update_data:
                    kb.is_active = update_data["is_active"]

                await session.flush()
                await session.refresh(kb)

            return KnowledgeBaseResponse.model_validate(kb)
        except SQLAlchemyError as e:
            logger.error(f"Error updating knowledge base: {e.args[0]}")
            raise e

    async def delete(self, kb_id: uuid.UUID) -> None:
        """Delete a knowledge base using ORM to trigger cascades"""
        try:
            async with DatabaseSession() as session:
                stmt = select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
                result = await session.execute(stmt)
                kb = result.scalar_one_or_none()

                if kb:
                    await session.delete(kb)
                    await session.commit()
        except SQLAlchemyError as e:
            logger.error(f"Error deleting knowledge base {kb_id}: {e.args[0]}")
            raise e

    async def list(
        self,
        request: KnowledgeBaseListRequest,
    ) -> KnowledgeBaseListResponse:
        """List knowledge bases with pagination and search"""
        try:
            async with DatabaseSession() as session:
                stmt = select(KnowledgeBase)
                if request.user_id:
                    stmt = stmt.where(KnowledgeBase.user_id == request.user_id)

                count_stmt = select(func.count()).select_from(stmt.subquery())
                total_result = await session.execute(count_stmt)
                total = total_result.scalar()

                stmt = stmt.order_by(KnowledgeBase.created_at.desc())
                stmt = stmt.offset(request.skip).limit(request.limit)

                result = await session.execute(stmt)
                kb_list = list(result.scalars().all())

                result_list = []
                for kb in kb_list:
                    kb_response = KnowledgeBaseResponse.model_validate(kb)
                    kb_response.document_count = await self.count_documents(kb.id)
                    result_list.append(kb_response)

            return await self.build_list_response(
                kb_list=result_list, total=total, skip=request.skip, limit=request.limit
            )
        except SQLAlchemyError as e:
            logger.error(f"Error listing knowledge bases: {e.args[0]}")
            raise e

    async def list_all(
        self,
        skip: int,
        limit: int,
    ) -> KnowledgeBaseListResponse:
        """List knowledge bases with pagination and search"""
        try:
            async with DatabaseSession() as session:
                stmt = select(KnowledgeBase)

                count_stmt = select(func.count()).select_from(stmt.subquery())
                total_result = await session.execute(count_stmt)
                total = total_result.scalar()

                stmt = stmt.order_by(KnowledgeBase.created_at.desc())
                stmt = stmt.offset(skip).limit(limit)

                result = await session.execute(stmt)
                kb_list = list(result.scalars().all())

                result_list = []
                for kb in kb_list:
                    kb_response = KnowledgeBaseResponse.model_validate(kb)
                    kb_response.document_count = await self.count_documents(kb.id)
                    result_list.append(kb_response)

            return await self.build_list_response(
                kb_list=result_list, total=total, skip=skip, limit=limit
            )
        except SQLAlchemyError as e:
            logger.error(f"Error listing knowledge bases: {e.args[0]}")
            raise e

    async def build_list_response(
        self,
        kb_list: List[KnowledgeBaseResponse],
        total: int,
        skip: int,
        limit: int,
    ) -> KnowledgeBaseListResponse:
        """Build a paginated list response"""
        return KnowledgeBaseListResponse(
            items=kb_list,
            total=total,
            skip=skip,
            limit=limit,
            has_more=(skip + len(kb_list) < total),
        )
