import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select, func
from src.db.models.document import Document
from .database_session import DatabaseSession
from src.models.common import PaginationParams, SearchParams
from src.models.document import (
    DocumentListResponse,
    DocumentProcessingStatusResponse,
    DocumentResponse,
    DocumentStatusEnum,
)
from src.utils.logger_conf import logger
from src.utils.decorators import singleton


@singleton
class DocumentRepository:
    """Service layer for Document operations"""

    async def create(
        self,
        knowledge_base_id: uuid.UUID,
        filename: str,
        original_filename: str,
        file_path: str,
        file_size: Optional[int],
        file_type: str,
        description: Optional[str] = None,
        mime_type: Optional[str] = None,
        uploaded_by: Optional[str] = None,
        id: Optional[uuid.UUID] = None,
        doc_metadata: Optional[Dict[str, Any]] = None,
    ) -> Document:
        """Create a new document"""
        try:
            async with DatabaseSession() as session:
                document = Document(
                    id=id,
                    knowledge_base_id=knowledge_base_id,
                    filename=filename,
                    original_filename=original_filename,
                    file_path=file_path,
                    file_size=file_size,
                    file_type=file_type,
                    mime_type=mime_type,
                    uploaded_by=uploaded_by,
                    status="pending",
                    doc_metadata=json.dumps(doc_metadata) if doc_metadata else None,
                )

                session.add(document)
                await session.flush()
                await session.refresh(document)
            return document
        except SQLAlchemyError as e:
            logger.error(f"Error creating document: {e.args[0]}")
            raise e

    async def bulk_create(self, documents_data: List[Dict[str, Any]]) -> List[Document]:
        """Create multiple documents in a single transaction"""
        try:
            async with DatabaseSession() as session:
                documents = []
                for doc_data in documents_data:
                    document = Document(
                        id=doc_data.get("id"),
                        knowledge_base_id=doc_data["knowledge_base_id"],
                        filename=doc_data["filename"],
                        original_filename=doc_data["original_filename"],
                        file_path=doc_data["file_path"],
                        file_size=doc_data.get("file_size"),
                        file_type=doc_data["file_type"],
                        mime_type=doc_data.get("mime_type"),
                        uploaded_by=doc_data.get("uploaded_by"),
                        status="pending",
                        doc_metadata=json.dumps(doc_data.get("doc_metadata"))
                        if doc_data.get("doc_metadata")
                        else None,
                    )
                    documents.append(document)

                session.add_all(documents)
                await session.flush()

                for document in documents:
                    await session.refresh(document)

            return documents
        except SQLAlchemyError as e:
            logger.error(f"Error bulk creating documents: {e.args[0]}")
            raise e

    async def get(self, document_id: uuid.UUID) -> Optional[Document]:
        """Get a document by ID"""
        try:
            async with DatabaseSession() as session:
                stmt = select(Document).where(Document.id == document_id)
                result = await session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"Error getting document: {e.args[0]}")
            raise e

    async def get_all_from_kb(self, kb_id: uuid.UUID) -> List[Document]:
        """Get all documents from a knowledge base"""
        try:
            async with DatabaseSession() as session:
                stmt = select(Document).where(Document.knowledge_base_id == kb_id)
                result = await session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"Error getting documents: {e.args[0]}")
            raise e

    async def count_documents_in_kb(self, kb_id: uuid.UUID) -> int:
        """Count documents in a knowledge base without fetching them"""
        try:
            async with DatabaseSession() as session:
                stmt = select(func.count(Document.id)).where(
                    Document.knowledge_base_id == kb_id
                )
                result = await session.execute(stmt)
                return result.scalar() or 0
        except SQLAlchemyError as e:
            logger.error(f"Error counting documents: {e.args[0]}")
            raise e

    async def get_multiple_status(
        self, document_ids: List[uuid.UUID]
    ) -> List[DocumentProcessingStatusResponse]:
        """Get processing status for multiple documents"""
        try:
            async with DatabaseSession() as session:
                stmt = select(Document).where(Document.id.in_(document_ids))
                result = await session.execute(stmt)
                documents = list(result.scalars().all())
            return [
                DocumentProcessingStatusResponse.model_validate(doc)
                for doc in documents
            ]
        except SQLAlchemyError as e:
            logger.error(f"Error getting documents status: {e.args[0]}")
            raise e

    async def get_status(
        self, document_id: uuid.UUID
    ) -> Optional[DocumentProcessingStatusResponse]:
        """Get document processing status"""
        try:
            document = await self.get(document_id)
            if not document:
                return None
            return DocumentProcessingStatusResponse.model_validate(document)
        except SQLAlchemyError as e:
            logger.error(f"Error getting document status: {e.args[0]}")
            raise e

    async def update_status(
        self,
        document_id: uuid.UUID,
        status: str,
        total_chunks: int = 0,
        error: Optional[str] = None,
    ) -> Optional[Document]:
        """Update document processing status"""
        try:
            async with DatabaseSession() as session:
                stmt = select(Document).where(Document.id == document_id)
                result = await session.execute(stmt)
                document = result.scalar_one_or_none()

                if not document:
                    return None

                document.status = status
                document.total_chunks = total_chunks

                if error:
                    document.processing_error = error

                if status in [DocumentStatusEnum.FINISHED, DocumentStatusEnum.FAILED]:
                    document.processed_at = datetime.now()

                await session.flush()
                await session.refresh(document)
            return document
        except SQLAlchemyError as e:
            logger.error(f"Error updating document status: {e.args[0]}")
            raise e

    async def update(
        self, document_id: uuid.UUID, update_data: Dict[str, Any]
    ) -> Optional[Document]:
        """Update document with dictionary of fields"""
        try:
            async with DatabaseSession() as session:
                stmt = select(Document).where(Document.id == document_id)
                result = await session.execute(stmt)
                document = result.scalar_one_or_none()

                if not document:
                    return None

                for key, value in update_data.items():
                    if key == "doc_metadata":
                        if isinstance(value, dict):
                            value = json.dumps(value)
                    setattr(document, key, value)

                await session.flush()
                await session.refresh(document)
            return document
        except SQLAlchemyError as e:
            logger.error(f"Error updating document: {e.args[0]}")
            raise e

    async def list(
        self,
        knowledge_base_id: uuid.UUID,
        pagination: PaginationParams,
        search: Optional[SearchParams] = None,
    ) -> DocumentListResponse:
        """List documents for a knowledge base with pagination and search"""
        try:
            async with DatabaseSession() as session:
                stmt = select(Document).where(
                    Document.knowledge_base_id == knowledge_base_id
                )
                if search and search.query:
                    search_filter = Document.filename.ilike(
                        f"%{search.query}%"
                    ) | Document.original_filename.ilike(f"%{search.query}%")
                    stmt = stmt.where(search_filter)

                if search and search.created_by is not None:
                    stmt = stmt.where(Document.uploaded_by == search.created_by)

                count_stmt = select(func.count()).select_from(stmt.subquery())
                total_result = await session.execute(count_stmt)
                total = total_result.scalar()

                stmt = stmt.order_by(Document.created_at.desc())
                stmt = stmt.offset(pagination.skip).limit(pagination.limit)

                result = await session.execute(stmt)
                doc_list = list(result.scalars().all())

                result_list = [DocumentResponse.model_validate(doc) for doc in doc_list]

            return DocumentListResponse(
                items=result_list,
                total=total,
                skip=pagination.skip,
                limit=pagination.limit,
                has_more=(pagination.skip + len(result_list) < total),
            )
        except SQLAlchemyError as e:
            logger.error(f"Error listing documents: {e.args[0]}")
            raise e

    async def delete_document(self, document_id: uuid.UUID) -> bool:
        """Delete a document using ORM to trigger cascades"""
        try:
            async with DatabaseSession() as session:
                stmt = select(Document).where(Document.id == document_id)
                result = await session.execute(stmt)
                document = result.scalar_one_or_none()

                if document:
                    await session.delete(document)
                    await session.commit()
                    return True
                return False
        except SQLAlchemyError as e:
            logger.error(f"Error deleting document: {e.args[0]}")
            raise e
