# src/rag/processors/file.py

from typing import Any

from src.core.config.celery_app import celery_app
from src.utils.decorators import singleton


@singleton
class FileProcessor:
    """
    File processor class to handle document processing.
    """

    @staticmethod
    def process_files(document_ids: str | list[str]) -> Any:
        """
        Start processing a document using Celery.

        Args:
            document_id: The ID of the document to process
            with_qa_generation: Whether to automatically queue QA generation after processing

        Returns:
            The task ID if the task was successfully queued, None otherwise
        """
        try:
            task = celery_app.send_task(
                "tasks.process_document",
                args=[document_ids],
                queue="document_processing",
            )
            return task.id
        except Exception:
            return None
