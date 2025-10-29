# src/tasks/cleanup.py
from typing import Any, Dict

from celery import shared_task

from src.database.repositories.document_repository import DocumentRepository
from src.domain.schemas.document import (
    DocumentProcessingStatusResponse,
    DocumentStatusEnum,
)
from src.infrastructure.events import get_event_publisher
from src.utils.constants import DOCUMENT_STATUS_CHANNEL
from src.utils.logger_conf import logger


@shared_task(
    bind=True,
    name="tasks.cleanup_timeout_documents",
    soft_time_limit=10 * 60 - 10,  # 10 minutes minus 10 seconds for cleanup
    time_limit=10 * 60,  # 10 minutes
    acks_late=True,
)
def cleanup_timeout_documents(self) -> Dict[str, Any]:
    """
    Cleanup documents that have been stuck in processing status for more than 1 hour.
    Sets them to timeout status and publishes events.

    Returns:
        A dictionary with the cleanup results
    """
    logger.info("Starting cleanup of timeout documents")

    doc_repo = DocumentRepository()

    event_publisher = get_event_publisher()

    try:
        # Find documents that have been processing for more than 1 hour
        stale_documents = doc_repo.find_stale_processing_documents(timeout_hours=1)

        if not stale_documents:
            logger.info("No timeout documents found")
            return {
                "status": "success",
                "timeout_documents_count": 0,
                "processed_documents": [],
            }

        logger.info(f"Found {len(stale_documents)} documents to timeout")

        processed_documents = []

        for document in stale_documents:
            try:
                # Update document status to timeout
                updated_document = doc_repo.update_status(
                    document_id=document.id,
                    status=DocumentStatusEnum.TIMEOUT,
                    error="Document processing exceeded time limit - automatically timed out by cleanup task",
                )

                if updated_document:
                    # Publish timeout event
                    event_publisher.publish(
                        DOCUMENT_STATUS_CHANNEL,
                        DocumentProcessingStatusResponse(
                            id=document.id,
                            filename=document.filename,
                            original_filename=document.original_filename,
                            status=DocumentStatusEnum.TIMEOUT,
                            total_chunks=document.total_chunks or 0,
                            processing_error=updated_document.processing_error,
                            processed_at=updated_document.processed_at,
                        ).model_dump(mode="json"),
                    )

                    processed_documents.append(
                        {
                            "document_id": str(document.id),
                            "filename": document.filename,
                            "created_at": document.created_at.isoformat(),
                            "updated_at": document.updated_at.isoformat(),
                        }
                    )

                    logger.info(
                        f"Timed out document {document.id} ({document.filename})"
                    )

            except Exception as e:
                logger.error(f"Error timing out document {document.id}: {str(e)}")
                continue

        logger.info(f"Successfully timed out {len(processed_documents)} documents")

        return {
            "status": "success",
            "timeout_documents_count": len(processed_documents),
            "processed_documents": processed_documents,
        }

    except Exception as e:
        logger.exception(f"Error during document cleanup: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "timeout_documents_count": 0,
            "processed_documents": [],
        }
