# src/tasks/file.py
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import random
import time
from typing import Any, Dict, List
import uuid
from zoneinfo import ZoneInfo

from celery import Task, shared_task
from celery.exceptions import SoftTimeLimitExceeded, WorkerLostError
from celery.signals import worker_process_init, worker_process_shutdown
import httpx
from langchain_core.documents import Document as LangchainDocument
import requests

from src.core.config.settings import settings
from src.database import document_repository
from src.database.models.document import Document as DBDocument
from src.domain.schemas.document import (
    DocumentProcessingStatusResponse,
    DocumentStatusEnum,
)
from src.infrastructure.events import get_event_publisher
from src.infrastructure.storage import minio_client
from src.rag.processors.strategy import get_strategy
from src.rag.vectorstores import vector_storage
from src.tasks.qac import generate_qa_pairs_async
from src.utils.constants import DOCUMENT_STATUS_CHANNEL
from src.utils.logger_conf import logger


_loop = None
_temp_files_cache = set()


@worker_process_init.connect
def init_worker_process(sender=None, **kwargs):
    """Initialize worker process with fresh event loop"""
    global _loop, _temp_files_cache
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _temp_files_cache = set()
    logger.info("Worker process initialized with fresh event loop")


@worker_process_shutdown.connect
def cleanup_worker_process(sender=None, **kwargs):
    """Cleanup worker process resources"""
    global _loop, _temp_files_cache

    for temp_file in _temp_files_cache.copy():
        try:
            if Path(temp_file).exists():
                os.remove(temp_file)
                logger.info(f"Cleaned up temp file: {temp_file}")
        except Exception as e:
            logger.error(f"Failed to cleanup temp file {temp_file}: {e}")

    if _loop and not _loop.is_closed():
        _loop.close()

    logger.info("Worker process cleaned up")


def get_or_create_eventloop():
    """Get or create event loop for current worker process"""
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop


@asynccontextmanager
async def temp_file_manager(document_id: uuid.UUID, filename: str):
    """Context manager for temporary file handling with automatic cleanup"""
    global _temp_files_cache

    temp_dir = Path(settings.temp_dir)
    temp_dir.mkdir(exist_ok=True)

    random_suffix = uuid.uuid4().hex[:8]
    file_extension = filename.split(".")[-1] if "." in filename else "tmp"
    temp_file_path = temp_dir / f"{document_id}_{random_suffix}.{file_extension}"

    try:
        _temp_files_cache.add(str(temp_file_path))
        yield temp_file_path
    finally:
        try:
            if temp_file_path.exists():
                os.remove(temp_file_path)
        except Exception as cleanup_error:
            logger.error(
                f"Error cleaning up temp file {temp_file_path}: {cleanup_error}"
            )
        finally:
            _temp_files_cache.discard(str(temp_file_path))


async def _process_document_async(
    document_id: uuid.UUID, retry_count: int = 0
) -> Dict[str, Any]:
    """Optimized async document processing with better error handling and resource management"""
    start_time = time.time()
    logger.info(f"Processing document {document_id} (attempt {retry_count + 1})")

    try:
        document = await document_repository.get(document_id)
        if not document:
            raise ValueError(f"Document with ID {document_id} not found")

        if document.status == DocumentStatusEnum.FINISHED:
            logger.warning(
                f"Document {document_id} has already been processed. Skipping."
            )
            return {
                "status": "skipped",
                "document_id": str(document_id),
                "reason": "Already processed",
            }

        document = await document_repository.update_status(
            document_id=document_id, status=DocumentStatusEnum.PROCESSING
        )

        await _publish_status_event(document, DocumentStatusEnum.PROCESSING, 0)

        async with temp_file_manager(document_id, document.filename) as temp_file_path:
            bucket_name = settings.minio_bucket
            download_start = time.time()

            await minio_client.get_file(
                bucket_name=bucket_name,
                object_name=document.file_path,
                file_path=str(temp_file_path),
            )

            download_time = time.time() - download_start
            file_size = temp_file_path.stat().st_size
            logger.info(f"Downloaded file ({file_size} bytes) in {download_time:.2f}s")

            strategy = get_strategy(document=document, config={})
            chunk_start = time.time()
            chunks, full_text = strategy.chunk(
                file_path=str(temp_file_path), document=document
            )
            chunk_time = time.time() - chunk_start

            if not chunks:
                logger.warning(f"No chunks extracted from document {document_id}")
            logger.info(f"Extracted {len(chunks)} chunks in {chunk_time:.2f}s")
            metadata_start = time.time()
            chunks = await _prepare_chunks_with_metadata(chunks, document)
            metadata_time = time.time() - metadata_start
            logger.info(
                f"Extracted metadata for {len(chunks)} chunks in {metadata_time:.2f}s"
            )

            await _generate_qa_pairs_with_error_handling(
                document_id, document.knowledge_base_id, chunks
            )

            storage_start = time.time()
            storage = vector_storage

            if document.processed_at:
                await storage.delete_chunks_by_doc_id(doc_id=str(document.id))

            if chunks:
                await storage.add_chunks(chunks)

            storage_time = time.time() - storage_start
            logger.info(f"Stored {len(chunks)} chunks in {storage_time:.2f}s")

            document = await document_repository.update(
                document_id=document_id,
                update_data={
                    "status": DocumentStatusEnum.FINISHED,
                    "total_chunks": len(chunks),
                    "processed_at": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")),
                    "full_text_content": full_text,
                },
            )

            await _publish_status_event(
                document, DocumentStatusEnum.FINISHED, len(chunks)
            )

            total_time = time.time() - start_time
            logger.info(
                f"Successfully processed document {document_id} in {total_time:.2f}s"
            )

            return {
                "status": "success",
                "document_id": str(document_id),
                "total_chunks": len(chunks),
                "kb_id": str(document.knowledge_base_id),
                "processing_time": total_time,
                "file_size": file_size,
            }

    except SoftTimeLimitExceeded:
        logger.warning(f"Processing of document {document_id} exceeded time limit")
        await _update_document_status(
            document_id, DocumentStatusEnum.FAILED, "Time limit exceeded"
        )
        return {
            "status": "timeout",
            "document_id": str(document_id),
            "error": "Time limit exceeded",
        }

    except Exception as e:
        logger.exception(f"Error processing document {document_id}: {str(e)}")
        await _update_document_status(document_id, DocumentStatusEnum.FAILED, str(e))
        return {
            "status": "failed",
            "document_id": str(document_id),
            "error": str(e),
        }


async def _prepare_chunks_with_metadata(
    chunks: List[LangchainDocument], document: DBDocument
) -> List[LangchainDocument]:
    """Process chunks and extract metadata for the document"""
    # try:
    #     extracted_metadata = extract_metadata_from_text_or_document(chunks)
    #     logger.info(f"Extracted metadata: {extracted_metadata}")
    # except Exception as e:
    #     logger.error(f"Error extracting metadata {e}")
    #     extracted_metadata = {}

    doc_metadata = json.loads(document.doc_metadata) if document.doc_metadata else {}
    for i, chunk in enumerate(chunks):
        start_index = chunk.metadata.get("start_index", 0)
        end_index = chunk.metadata.get("end_index", 0)
        metadata = {
            "chunk_index": i,
            "filename": document.filename,
            "kb_id": str(document.knowledge_base_id),
            "document_id": str(document.id),
            "original_filename": document.original_filename,
            # **extracted_metadata,
            "start_index": start_index,
            "end_index": end_index,
            **doc_metadata,
        }

        chunk.metadata = metadata

    return chunks


async def _generate_qa_pairs_with_error_handling(
    document_id: uuid.UUID, kb_id: uuid.UUID, chunks: List[LangchainDocument]
):
    """Generate QA pairs with error handling - don't fail main processing"""
    try:
        number_of_chunks = min(8, len(chunks))
        random_chunks = (
            random.sample(chunks, number_of_chunks)
            if len(chunks) > number_of_chunks
            else chunks
        )

        qa_contexts = [
            chunk.page_content for chunk in random_chunks if chunk.page_content
        ]

        if qa_contexts:
            await generate_qa_pairs_async(document_id, kb_id, qa_contexts)
            logger.info(f"Generated QA pairs for document {document_id}")
    except Exception as e:
        logger.error(f"Failed to generate QA pairs for document {document_id}: {e}")


async def _publish_status_event(
    document: DBDocument, status: DocumentStatusEnum, total_chunks: int
):
    """Publish document status event"""
    try:
        event_publisher = await get_event_publisher()
        await event_publisher.publish(
            DOCUMENT_STATUS_CHANNEL,
            DocumentProcessingStatusResponse(
                id=document.id,
                filename=document.filename,
                original_filename=document.original_filename,
                status=status,
                total_chunks=total_chunks,
                processing_error=getattr(document, "processing_error", None),
                processed_at=getattr(document, "processed_at", None),
            ).model_dump(mode="json"),
        )
        await event_publisher.disconnect()
    except Exception as e:
        await event_publisher.disconnect()
        logger.error(f"Failed to publish status event: {e}")


async def _update_document_status(
    document_id: uuid.UUID,
    status: DocumentStatusEnum,
    error: str = None,
    total_chunks: int = 0,
) -> DBDocument:
    """Update document status and publish event"""
    update_data = {"status": status}

    if error:
        update_data["processing_error"] = error

    if status == DocumentStatusEnum.FINISHED:
        update_data["total_chunks"] = total_chunks
        update_data["processed_at"] = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))

    document = await document_repository.update(
        document_id=document_id, update_data=update_data
    )

    await _publish_status_event(document, status, total_chunks)
    return document


@shared_task(
    bind=True,
    name="tasks.process_document",
    soft_time_limit=45 * 60,
    time_limit=50 * 60,
    acks_late=True,
    track_started=True,
    autoretry_for=[
        httpx.TimeoutException,
        httpx.NetworkError,
        requests.exceptions.RequestException,
        ConnectionError,
        WorkerLostError,
    ],
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
    queue="document_processing",
)
def process_document(self: Task, document_id: str) -> Dict[str, Any]:
    """
    Process a document using the specified strategy.

    Args:
        document_id: The ID of the document to process

    Returns:
        A dictionary with the processing results
    """
    doc_uuid = uuid.UUID(document_id) if isinstance(document_id, str) else document_id
    retry_count = self.request.retries

    try:
        self.update_state(
            state="PROGRESS",
            meta={"current": 0, "total": 100, "status": "Starting processing..."},
        )

        loop = get_or_create_eventloop()
        result = loop.run_until_complete(_process_document_async(doc_uuid, retry_count))

        self.update_state(
            state="SUCCESS", meta={"current": 100, "total": 100, "result": result}
        )

        return result

    except SoftTimeLimitExceeded:
        logger.warning(f"Document {doc_uuid} processing exceeded soft time limit")
        if retry_count < self.max_retries:
            logger.info(f"Retrying document {doc_uuid}. Attempt {retry_count + 1}")
            countdown = min(30 * (2**retry_count), 120)
            raise self.retry(exc=SoftTimeLimitExceeded, countdown=countdown)
        else:
            loop = get_or_create_eventloop()
            loop.run_until_complete(
                _update_document_status(doc_uuid, DocumentStatusEnum.TIMEOUT)
            )
            raise

    except Exception as e:
        logger.exception(f"Error processing document {doc_uuid}: {str(e)}")

        if isinstance(e, (ValueError, FileNotFoundError)):
            loop = get_or_create_eventloop()
            loop.run_until_complete(
                _update_document_status(doc_uuid, DocumentStatusEnum.FAILED, str(e))
            )
            return {
                "status": "failed",
                "document_id": str(doc_uuid),
                "error": str(e),
            }

        if retry_count < self.max_retries:
            countdown = min(60 * (2**retry_count), 300)
            raise self.retry(exc=e, countdown=countdown)

        raise


@shared_task(name="tasks.cleanup_temp_files")
def cleanup_temp_files():
    """Cleanup orphaned temporary files"""
    temp_dir = Path(settings.temp_dir)
    if not temp_dir.exists():
        return {"cleaned": 0}

    cleaned = 0
    cutoff_time = time.time() - 3600

    for temp_file in temp_dir.glob("*"):
        try:
            if temp_file.stat().st_mtime < cutoff_time:
                temp_file.unlink()
                cleaned += 1
        except Exception as e:
            logger.error(f"Error cleaning up {temp_file}: {e}")

    logger.info(f"Cleaned up {cleaned} orphaned temporary files")
    return {"cleaned": cleaned}
