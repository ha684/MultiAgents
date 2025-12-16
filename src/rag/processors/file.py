# src/rag/processors/file.py
"""
File Processor - Document Processing Interface

This module provides an interface for processing documents using Celery tasks.
Uses the centralized TaskClient for task management.
"""

from typing import Any

from src.infrastructure.tasks import task_client
from src.utils.decorators import singleton


@singleton
class FileProcessor:
    """
    File processor class to handle document processing.

    Uses the centralized TaskClient for queuing tasks.
    """

    @staticmethod
    def process_file(document_id: str) -> str | None:
        """
        Start processing a single document using Celery.

        Args:
            document_id: The ID of the document to process

        Returns:
            The task ID if the task was successfully queued, None otherwise
        """
        return task_client.process_document(document_id)

    @staticmethod
    def process_files(document_ids: str | list[str]) -> Any:
        """
        Start processing document(s) using Celery.

        Args:
            document_ids: Single document ID or list of document IDs to process

        Returns:
            For single ID: The task ID if successfully queued, None otherwise
            For list: List of task IDs for successfully queued tasks
        """
        if isinstance(document_ids, str):
            return task_client.process_document(document_ids)
        else:
            return task_client.process_documents_batch(document_ids)

    @staticmethod
    def get_task_status(task_id: str) -> dict[str, Any]:
        """
        Get the status of a document processing task.

        Args:
            task_id: The task ID to check

        Returns:
            Dictionary with task status information
        """
        return task_client.get_task_status(task_id)

    @staticmethod
    def cancel_task(task_id: str) -> bool:
        """
        Cancel a document processing task.

        Args:
            task_id: The task ID to cancel

        Returns:
            True if cancellation was sent successfully
        """
        return task_client.revoke_task(task_id, terminate=True)
