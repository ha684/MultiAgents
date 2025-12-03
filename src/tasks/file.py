import json
import os
import random
import uuid
from pathlib import Path
from typing import Any, Dict

import httpx
import requests
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from langchain_core.documents import Document

from src.core.config.settings import settings
from src.database import get_db
from src.database.models.document import (
    DocumentProcessingStatusResponse,
    DocumentStatusEnum,
)
from src.database.repositories.document_repository import DocumentRepository
from src.infrastructure.events import get_event_publisher
from src.infrastructure.storage.minio_client import MinioClient
from src.rag.processors.strategy import get_strategy
from src.rag.vectorstores import vector_storage
from src.tasks.qac import generate_qa_pairs
from src.utils import generate_chunk_id
from src.utils.constants import DOCUMENT_STATUS_CHANNEL
from src.utils.logger_conf import logger


@shared_task(
    bind=True,
    name="tasks.process_document",
    soft_time_limit=60 * 60 - 10,  # 1 hour minus 10 seconds for cleanup
    time_limit=60 * 60,  # 1 hour
    acks_late=True,
    autoretry_for=[
        httpx.TimeoutException,
        httpx.NetworkError,
        requests.exceptions.RequestException,
    ],
    reject_on_worker_lost=True,
    retry_backoff=True,
    max_retries=3,
)
def process_document(self, document_id: uuid.UUID) -> Dict[str, Any]:
    """
    Process a document using the specified strategy.

    Args:
        document_id: The ID of the document to process
        strategy_name: The name of the strategy to use (default: "naive")

    Returns:
        A dictionary with the processing results
    """

    logger.info(f"Processing document {document_id}")

    # Get DB session
    db = next(get_db())
    doc_repo = DocumentRepository(db)

    tmp_file_path: Path | None = None

    event_publisher = get_event_publisher()

    try:
        # Update document status to processing
        document = doc_repo.update_status(
            document_id=document_id, status=DocumentStatusEnum.PROCESSING
        )

        if not document:
            raise ValueError(f"Document with ID {document_id} not found")

        event_publisher.publish(
            DOCUMENT_STATUS_CHANNEL,
            DocumentProcessingStatusResponse(
                id=document_id,
                filename=document.filename,
                original_filename=document.original_filename,
                status=DocumentStatusEnum.PROCESSING,
                total_chunks=0,
                processing_error=None,
                processed_at=None,
            ).model_dump(mode="json"),
        )

        # Download file from storage
        minio_client = MinioClient(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

        # Create temporary directory for downloaded file
        temp_dir = Path(settings.temp_dir)
        os.makedirs(temp_dir, exist_ok=True)
        random_suffix = uuid.uuid4().hex
        file_extension = document.filename.split(".")[-1]
        local_file_path = temp_dir / f"{document_id}_{random_suffix}.{file_extension}"

        # Get file from Minio
        bucket_name = settings.minio_bucket
        minio_client.get_file(
            bucket_name=bucket_name,
            object_name=document.file_path,
            file_path=str(local_file_path),
        )
        # convert xls to xlsx
        if file_extension == "xls":
            from src.utils.xls_converter import convert_to_xlsx

            original = local_file_path
            local_file_path = convert_to_xlsx(original)
            os.remove(original)
        # Set the temporary file path for cleanup
        tmp_file_path = local_file_path

        # Get the configuration for processing from the knowledge base
        kb_config = {}

        strategy = get_strategy(document=document, config=kb_config)

        # Process document with the strategy
        chunks = strategy.chunk(file_path=str(local_file_path), document=document)

        doc_metadata: dict[str, Any] = {}
        try:
            doc_metadata = json.loads(document.doc_metadata or "{}") or {}
        except json.JSONDecodeError as e:
            logger.error(
                f"Error decoding document metadata for document {document_id}: {str(e)}"
            )

        # Add the document description as a separate chunk if it exists
        if document.description:
            description_chunk = Document(
                page_content=document.description,
                metadata={
                    "is_description": True,
                },
            )
            chunks.insert(0, description_chunk)

        # Add metadata to chunks
        for i, chunk in enumerate(chunks):
            sheet_name = chunk.metadata.get("sheet_name")
            chunk.metadata = {
                **(doc_metadata),
                "filename": document.filename,
                "images": chunk.metadata.get("images", []),
                "kb_id": str(document.knowledge_base_id),
                "document_id": str(document.id),
                "original_filename": document.original_filename,
            }
            if sheet_name is not None:
                chunk.metadata["sheet_name"] = sheet_name

            chunk_id = f"{document_id}:{i}"
            # Generate a unique deteministic UUID for the each chunk
            chunk.id = generate_chunk_id(str(document.id), chunk_id)
        # Save processed chunks
        storage = vector_storage

        if document.processed_at:
            storage.delete_chunks_by_doc_id(doc_id=str(document.id))

        storage.add_chunks(chunks)

        logger.info(f"Processed {len(chunks)} chunks for document {document_id}")

        random_chunks = chunks
        if len(chunks) > 5:
            # Randomly sample 5 chunks for QA generation
            random_chunks = random.sample(chunks, 5)

        if not random_chunks:
            logger.warning(
                f"No valid chunks found for document {document_id}, skipping QA generation"
            )
        else:
            chunk_contexts = [
                chunk.page_content for chunk in random_chunks if chunk.page_content
            ]
            generate_qa_pairs.delay(
                document_id=document.id,
                kb_id=document.knowledge_base_id,
                contexts=chunk_contexts,
            )

        # Update document status to processed
        document = doc_repo.update(
            document_id=document_id,
            update_data={
                "status": DocumentStatusEnum.FINISHED,
                "total_chunks": len(chunks),
                "processed_at": document.processed_at,
            },
        )
        assert document is not None, "Document should not be None after update"

        event_publisher.publish(
            DOCUMENT_STATUS_CHANNEL,
            DocumentProcessingStatusResponse(
                id=document_id,
                filename=document.filename,
                original_filename=document.original_filename,
                status=DocumentStatusEnum.FINISHED,
                total_chunks=len(chunks),
                processing_error=None,
                processed_at=document.processed_at,
            ).model_dump(mode="json"),
        )

        return {
            "status": "success",
            "document_id": document_id,
            "total_chunks": len(chunks),
        }

    except SoftTimeLimitExceeded:
        logger.warning(f"Processing of document {document_id} exceeded time limit")

        # Update document status to failed due to timeout
        document = doc_repo.update_status(
            document_id=document_id,
            status=DocumentStatusEnum.TIMEOUT,
            error="Processing exceeded time limit",
        )

        assert document is not None, "Document should not be None after update"
        event_publisher.publish(
            DOCUMENT_STATUS_CHANNEL,
            DocumentProcessingStatusResponse(
                id=document_id,
                filename=document.filename,
                original_filename=document.original_filename,
                status=DocumentStatusEnum.TIMEOUT,
                total_chunks=0,
                processing_error=document.processing_error,
                processed_at=document.processed_at,
            ).model_dump(mode="json"),
        )

        return {
            "status": "timeout",
            "document_id": document_id,
            "error": "Time limit exceeded",
        }

    except Exception as e:
        logger.exception(f"Error processing document {document_id}: {str(e)}")

        # Update document status to failed
        document = doc_repo.update_status(
            document_id=document_id,
            status=DocumentStatusEnum.FAILED,
            error=str(e),
        )

        if document:
            event_publisher.publish(
                DOCUMENT_STATUS_CHANNEL,
                DocumentProcessingStatusResponse(
                    id=document_id,
                    filename=document.filename,
                    original_filename=document.original_filename,
                    status=DocumentStatusEnum.FAILED,
                    total_chunks=0,
                    processing_error=str(e),
                    processed_at=None,
                ).model_dump(mode="json"),
            )

        return {
            "status": DocumentStatusEnum.FAILED,
            "document_id": document_id,
            "error": str(e),
        }
    finally:
        # Clean up temporary file if it exists
        if tmp_file_path and tmp_file_path.exists():
            try:
                os.remove(tmp_file_path)
            except Exception as cleanup_error:
                logger.error(
                    f"Error cleaning up temporary file {tmp_file_path}: {str(cleanup_error)}"
                )

        # Close DB session
        db.close()
