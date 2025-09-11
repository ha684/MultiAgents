from uuid import UUID
from src.db.models.document import Document, DocumentQA
from src.db.repository.database_session import DatabaseSession
from sqlalchemy import func, select
from src.utils.logger_conf import logger
from sqlalchemy.exc import SQLAlchemyError
from src.utils.decorators import singleton


@singleton
class QARepository:
    """Service layer for QA operations"""

    async def get_qa_by_doc_id(self, doc_id: UUID):
        try:
            async with DatabaseSession() as session:
                query = select(DocumentQA).filter(DocumentQA.document_id == doc_id)
                result = await session.execute(query)
            return result.scalars().all()
        except SQLAlchemyError as e:
            logger.error(f"Error getting QA by document ID: {e.args[0]}")
            raise e

    async def get_qa_by_kb_id(self, kb_id: UUID):
        """Get all QAs associated with a knowledge base where the document is active (is_inactive == False or None)"""
        try:
            async with DatabaseSession() as session:
                query = (
                    select(DocumentQA)
                    .filter(DocumentQA.kb_id == kb_id)
                    .join(DocumentQA.document)
                    .filter(
                        Document.is_inactive.is_(False) | Document.is_inactive.is_(None)
                    )
                )

                result = await session.execute(query)
            return result.scalars().all()
        except SQLAlchemyError as e:
            logger.error(f"Error getting QA by knowledge base ID: {e.args[0]}")
            raise e

    async def get_qa_by_id(self, qa_id: UUID):
        try:
            async with DatabaseSession() as session:
                query = select(DocumentQA).filter(DocumentQA.id == qa_id)
                result = await session.execute(query)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"Error getting QA by ID: {e.args[0]}")
            raise e

    async def create_qa(self, qa: DocumentQA):
        try:
            async with DatabaseSession() as session:
                session.add(qa)
                await session.commit()
                await session.refresh(qa)
            return qa
        except SQLAlchemyError as e:
            logger.error(f"Error creating QA: {e.args[0]}")
            raise e

    async def create_qa_list(self, qa_list: list[DocumentQA]):
        try:
            if not qa_list:
                return []
            async with DatabaseSession() as session:
                session.add_all(qa_list)
                await session.commit()
                for qa in qa_list:
                    await session.refresh(qa)
            return qa_list
        except SQLAlchemyError as e:
            logger.error(f"Error creating QA list: {e.args[0]}")
            raise e

    async def delete_qa(self, qa_id: UUID):
        try:
            async with DatabaseSession() as session:
                qa = await self.get_qa_by_id(qa_id)
                if qa:
                    await session.delete(qa)
                    await session.commit()
            return True
        except SQLAlchemyError as e:
            logger.error(f"Error deleting QA: {e.args[0]}")
            raise e

    async def delete_qa_by_doc_id(self, doc_id: UUID):
        try:
            async with DatabaseSession() as session:
                qas = await self.get_qa_by_doc_id(doc_id)
                if not qas:
                    return False
                for qa in qas:
                    await session.delete(qa)
                await session.commit()
            return True
        except SQLAlchemyError as e:
            logger.error(f"Error deleting QA by document ID: {e.args[0]}")
            raise e

    async def delete_qa_by_kb_id(self, kb_id: UUID):
        try:
            async with DatabaseSession() as session:
                qas = await self.get_qa_by_kb_id(kb_id)
                if not qas:
                    return False
                for qa in qas:
                    await session.delete(qa)
                await session.commit()
            return True
        except SQLAlchemyError as e:
            logger.error(f"Error deleting QA by knowledge base ID: {e.args[0]}")
            raise e

    async def get_random_qa_by_kb_id(self, kb_id: UUID, limit: int = 5):
        """
        Get a random set of QA pairs associated with a knowledge base.

        Args:
            kb_id (UUID): The ID of the knowledge base.
            limit (int): The maximum number of QA pairs to return.

        Returns:
            List[DocumentQA]: A list of random QA pairs.
        """
        try:
            async with DatabaseSession() as session:
                query = (
                    select(DocumentQA)
                    .filter(DocumentQA.kb_id == kb_id)
                    .join(DocumentQA.document)
                    .filter(
                        Document.is_inactive.is_(False) | Document.is_inactive.is_(None)
                    )
                    .order_by(func.random())
                    .limit(limit)
                )
                result = await session.execute(query)
            return result.scalars().all()
        except SQLAlchemyError as e:
            logger.error(f"Error getting random QA by knowledge base ID: {e.args[0]}")
            raise e
