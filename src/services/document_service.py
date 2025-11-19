# src/services/document_service.py
import io
import uuid
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import UploadFile
from qdrant_client import models

from src.core.config.settings import settings
from src.core.exceptions.chat_exceptions import ValidationError
from src.core.exceptions.document_exceptions import (
    DocumentNotFoundError,
    DocumentProcessingError,
    DuplicateDocumentError,
)
from src.database import document_repository, knowledge_base_repository, qa_repository
from src.database.models.document import Document
from src.domain.schemas.document import (
    DocumentListResponse,
    DocumentProcessingStatusResponse,
    DocumentStatusEnum,
    PaginationParams,
    SearchParams,
)
from src.domain.schemas.qa import DocumentQAResponse
from src.infrastructure.storage import minio_client
from src.rag.processors.file import FileProcessor
from src.rag.vectorstores import vector_retrieval, vector_storage
from src.services.metadata_extractor import (
    aggregate_related_documents_with_reasons,
    build_metadata_filters,
    build_search_query_from_metadata,
    combine_filters,
)
from src.utils.decorators import singleton
from src.utils.hash_calculator import calculate_hash_from_stream
from src.utils.logger_conf import logger


@singleton
class DocumentService:
    def __init__(self):
        self.document_repository = document_repository
        self.kb_repository = knowledge_base_repository
        self.qa_repository = qa_repository
        self.file_processor = FileProcessor()

    async def _verify_knowledge_base_exists(self, knowledge_base_id: uuid.UUID) -> None:
        """Verify that a knowledge base exists."""
        try:
            await self.kb_repository.get(knowledge_base_id)
        except Exception as e:
            logger.error(f"Error verifying knowledge base: {str(e)}")
            raise e

    async def _get_file_info(self, file: UploadFile) -> tuple[str, str]:
        """Extract file information without saving to disk."""
        if not file.filename:
            raise ValidationError(message="Invalid file upload. Filename is required.")

        file_extension = Path(file.filename).suffix.lower()
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_type = file_extension.lstrip(".")

        return unique_filename, file_type

    async def _upload_to_minio(
        self,
        file: UploadFile,
        knowledge_base_id: uuid.UUID,
        unique_filename: str,
    ) -> tuple[str, int]:
        """Upload file directly to MinIO without temporary file."""
        bucket_name = settings.minio_bucket
        minio_object_path = f"{knowledge_base_id}/{unique_filename}"

        file_content = await file.read()
        file_size = len(file_content)

        await file.seek(0)

        file_stream = io.BytesIO(file_content)

        await minio_client.upload_file(
            bucket_name=bucket_name,
            object_name=minio_object_path,
            data=file_stream,
            length=file_size,
            content_type=file.content_type or "application/octet-stream",
        )

        return minio_object_path, file_size

    async def upload_and_process_document(
        self,
        knowledge_base_id: uuid.UUID,
        file: UploadFile,
        tenant_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[Document, str]:
        """Upload a document and queue it for processing with retry support for failed documents."""
        await self._verify_knowledge_base_exists(knowledge_base_id)
        content_hash = await calculate_hash_from_stream(file)
        existing_document = await self.document_repository.find_by_hash(
            knowledge_base_id, content_hash
        )

        if existing_document:
            if existing_document.status == DocumentStatusEnum.FAILED:
                logger.info(
                    f"Found failed document {existing_document.id} with same hash. "
                    f"Resetting status to PENDING for retry."
                )

                await self.document_repository.update(
                    document_id=existing_document.id,
                    update_data={
                        "status": DocumentStatusEnum.PENDING,
                        "processing_error": None,
                        "updated_at": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")),
                    },
                )

                task_id = self.file_processor.process_files(str(existing_document.id))

                if not task_id:
                    logger.error(
                        f"Failed to queue document {existing_document.id} for reprocessing"
                    )
                    raise DocumentProcessingError(
                        message="Failed to queue document for reprocessing"
                    )

                logger.info(
                    f"Document {existing_document.id} queued for reprocessing with task ID {task_id}"
                )

                return existing_document, task_id

            elif existing_document.status in [
                DocumentStatusEnum.FINISHED,
                DocumentStatusEnum.PROCESSING,
                DocumentStatusEnum.PENDING,
            ]:
                raise DuplicateDocumentError(
                    message=f"Document with identical content already exists as '{existing_document.original_filename}' "
                    f"with status '{existing_document.status}'."
                )

        try:
            unique_filename, file_type = await self._get_file_info(file)
            minio_object_path, file_size = await self._upload_to_minio(
                file, knowledge_base_id, unique_filename
            )

            document = await self.document_repository.create(
                knowledge_base_id=knowledge_base_id,
                filename=unique_filename,
                original_filename=file.filename or "unknown",
                file_path=minio_object_path,
                file_size=file_size,
                file_type=file_type,
                mime_type=file.content_type,
                uploaded_by=tenant_id,
                doc_metadata=metadata,
                content_hash=content_hash,
            )

            task_id = self.file_processor.process_files(str(document.id))

            if not task_id:
                logger.error(f"Failed to queue document {document.id} for processing")
                raise DocumentProcessingError(
                    message="Failed to queue document for processing"
                )

            logger.info(
                f"Document {document.id} queued for processing with task ID {task_id}"
            )

            return document, task_id

        except Exception as e:
            logger.exception(f"Error uploading document: {str(e)}")
            raise DocumentProcessingError(
                message=f"Failed to upload document: {str(e)}"
            )

    async def get_document(self, document_id: uuid.UUID) -> Document:
        """Get document details."""
        document = await self.document_repository.get(document_id)
        if not document:
            raise DocumentNotFoundError(message="Document not found")
        return document

    async def get_document_status(
        self, document_id: uuid.UUID
    ) -> DocumentProcessingStatusResponse | None:
        """Get document processing status."""
        status = await self.document_repository.get_status(document_id)
        if not status:
            raise DocumentNotFoundError(message="Document not found")
        return status

    async def get_multiple_document_status(self, document_ids: list[uuid.UUID]):
        """Get processing status for multiple documents."""
        if not document_ids:
            raise ValidationError(message="Document IDs are required")

        statuses = await self.document_repository.get_multiple_status(document_ids)
        if not statuses:
            raise DocumentNotFoundError(
                message="No documents found with the provided IDs"
            )
        return statuses

    async def list_documents(
        self,
        knowledge_base_id: uuid.UUID,
        pagination: PaginationParams,
        search: SearchParams | None = None,
    ) -> DocumentListResponse:
        """List documents in a knowledge base."""
        await self._verify_knowledge_base_exists(knowledge_base_id)

        result = await self.document_repository.list(
            knowledge_base_id, pagination, search
        )
        return result

    async def delete_document(self, document_id: uuid.UUID) -> None:
        """Delete a document."""
        document = await self.document_repository.get(document_id)
        if not document:
            raise DocumentNotFoundError(message="Document not found")

        try:
            if document.total_chunks > 0:
                await vector_storage.delete_chunks_by_doc_id(str(document_id))
            await self.document_repository.delete_document(document_id)

        except Exception as e:
            logger.exception(f"Unexpected error deleting document: {str(e)}")
            raise e

    async def toggle_document_active(
        self, document_id: uuid.UUID, active: bool
    ) -> Document:
        """Activate or deactivate a document."""
        document = await self.document_repository.get(document_id)
        if not document:
            raise DocumentNotFoundError(message="Document not found")

        try:
            if document.status != DocumentStatusEnum.FINISHED:
                raise ValidationError(
                    message="Document must be processed before it can be activated/deactivated",
                )

            if document.total_chunks == 0:
                raise ValidationError(
                    message="Document has no chunks, cannot toggle active status",
                )

            updated_document = await self.document_repository.update(
                document_id=document_id, update_data={"is_inactive": not active}
            )
            if not updated_document:
                raise DocumentProcessingError(
                    message="Failed to update document status"
                )

            await vector_storage.update_chunks_status_by_doc_id(
                doc_id=str(document_id), active=active
            )

            return updated_document
        except Exception as e:
            logger.exception(f"Error updating document status: {str(e)}")
            raise DocumentProcessingError(message="Failed to update document status")

    async def get_document_qa_pairs(
        self, document_id: uuid.UUID
    ) -> Sequence[DocumentQAResponse]:
        """Get question-answer pairs for a document."""
        qa_pairs = await self.qa_repository.get_qa_by_doc_id(document_id)
        if not qa_pairs:
            raise DocumentNotFoundError(message="No QA pairs found for this document")
        return qa_pairs

    # async def get_related_document_ids(
    #     self,
    #     document_id: str,
    #     kb_id: str,
    #     num_sample_chunks: int = 3,
    #     score_threshold: float = 0.5,
    #     embed_top: int = 10,
    #     rerank_top: int = 0,
    #     filters: Optional[models.Filter] = None,
    # ) -> List[Dict]:
    #     """
    #     Get related document IDs.
    #     """
    #     try:
    #         source_chunks = await vector_storage.get_chunks_by_doc_id(document_id)

    #         if not source_chunks:
    #             logger.warning(f"No chunks found for document {document_id}")
    #             return []

    #         sampled_chunks = self._sample_representative_chunks(
    #             chunks=source_chunks,
    #             sample_count=num_sample_chunks,
    #             document_id=document_id,
    #         )
    #         logger.info(
    #             f"Sampled {len(sampled_chunks)} chunks from document {document_id}"
    #         )

    #         related_document_scores = defaultdict(list)

    #         retrieval_tasks = []
    #         for i, chunk in enumerate(sampled_chunks):
    #             chunk_content = chunk.page_content
    #             chunk_id = chunk.metadata.get("_id", f"chunk_{i}")

    #             task = vector_retrieval.retrieve(
    #                 kb_id=kb_id,
    #                 query=chunk_content,
    #                 top_k=embed_top,
    #                 top_n=rerank_top,
    #                 filters=filters,
    #             )
    #             retrieval_tasks.append((task, i, chunk_id))

    #         retrieval_results = await asyncio.gather(
    #             *[task for task, _, _ in retrieval_tasks], return_exceptions=True
    #         )

    #         for (_, i, chunk_id), related_chunks in zip(
    #             retrieval_tasks, retrieval_results
    #         ):
    #             if isinstance(related_chunks, Exception):
    #                 continue

    #             for related_chunk in related_chunks:
    #                 related_doc_id = related_chunk.metadata.get("document_id")
    #                 vector_score = related_chunk.metadata.get("vector_score", 0.0)

    #                 if related_doc_id == document_id or vector_score < score_threshold:
    #                     continue

    #                 related_document_scores[related_doc_id].append(
    #                     {
    #                         "score": vector_score,
    #                         "source_chunk_id": chunk_id,
    #                         "related_chunk_id": related_chunk.metadata.get("_id"),
    #                         "sample_index": i,
    #                     }
    #                 )

    #         final_results = self._aggregate_and_rank_documents(
    #             related_document_scores, len(sampled_chunks)
    #         )

    #         logger.info(
    #             f"Found {len(final_results)} related documents for {document_id}"
    #         )
    #         return final_results

    #     except Exception as e:
    #         logger.error(f"Error finding related documents for {document_id}: {e}")
    #         return []

    # def _sample_representative_chunks(
    #     self, chunks: List[Document], sample_count: int, document_id: str
    # ) -> List[Document]:
    #     """
    #     Sample representative chunks from the document.
    #     """
    #     if len(chunks) <= sample_count:
    #         return chunks

    #     representative_chunks = []
    #     if chunks:
    #         representative_chunks.append(chunks[0])
    #     if len(chunks) > 1 and len(representative_chunks) < sample_count:
    #         longest_chunk = max(chunks[1:], key=lambda x: len(x.page_content))
    #         representative_chunks.append(longest_chunk)
    #     if len(chunks) >= 5 and len(representative_chunks) < sample_count:
    #         middle_idx = len(chunks) // 2
    #         if chunks[middle_idx] not in representative_chunks:
    #             representative_chunks.append(chunks[middle_idx])

    #     remaining_slots = sample_count - len(representative_chunks)
    #     if remaining_slots > 0:
    #         used_chunks = set(id(chunk) for chunk in representative_chunks)
    #         available_chunks = [
    #             chunk for chunk in chunks if id(chunk) not in used_chunks
    #         ]

    #         if available_chunks:
    #             seed = int(hashlib.md5(document_id.encode()).hexdigest(), 16)
    #             random.seed(seed)
    #             additional_samples = random.sample(
    #                 available_chunks, min(remaining_slots, len(available_chunks))
    #             )
    #             representative_chunks.extend(additional_samples)

    #     return representative_chunks[:sample_count]

    # def _aggregate_and_rank_documents(
    #     self, document_scores: Dict[str, List[Dict]], total_sampled_chunks: int
    # ) -> List[Dict]:
    #     """
    #     Aggregate scores from multiple chunk queries and rank documents.
    #     """
    #     results = []

    #     for doc_id, score_records in document_scores.items():
    #         scores = [record["score"] for record in score_records]
    #         unique_matching_chunks = len(
    #             set(record["sample_index"] for record in score_records)
    #         )
    #         chunk_coverage_ratio = unique_matching_chunks / total_sampled_chunks

    #         avg_score = sum(scores) / len(scores)
    #         chunk_coverage_bonus = min(chunk_coverage_ratio, 1.0) * 0.2
    #         final_score = avg_score + chunk_coverage_bonus
    #         total_matches = len(score_records)

    #         results.append(
    #             {
    #                 "document_id": doc_id,
    #                 "final_score": final_score,
    #                 "total_matches": total_matches,
    #                 "unique_matching_chunks": unique_matching_chunks,
    #                 "chunk_coverage_ratio": chunk_coverage_ratio,
    #             }
    #         )

    #     results.sort(key=lambda x: x["final_score"], reverse=True)
    #     return results

    async def get_related_document_ids(
        self,
        document_id: str,
        kb_id: str,
        score_threshold: float = 0.5,
        embed_top: int = 10,
        rerank_top: int = 0,
        filters: models.Filter | None = None,
        **kwargs: Any,
    ) -> list[dict]:
        """
        Get related document IDs using metadata-based filtering + vector search
        """
        try:
            source_chunks = await vector_storage.get_chunks_by_doc_id(
                document_id, limit=1
            )
            if not source_chunks:
                logger.warning(f"No chunks found for document {document_id}")
                return []

            source_metadata = source_chunks[0].metadata
            metadata_filters = build_metadata_filters(source_metadata)
            combined_filters = combine_filters(filters, metadata_filters)
            search_query = build_search_query_from_metadata(source_metadata)
            related_chunks = await vector_retrieval.retrieve(
                kb_id=kb_id,
                query=search_query,
                top_k=embed_top,
                top_n=rerank_top,
                filters=combined_filters,
            )

            related_documents = aggregate_related_documents_with_reasons(
                related_chunks, source_metadata, document_id, score_threshold
            )

            logger.info(
                f"Found {len(related_documents)} related documents for {document_id}"
            )
            return related_documents

        except Exception as e:
            logger.error(f"Error finding related documents for {document_id}: {e}")
            raise e
