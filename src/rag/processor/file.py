from typing import List
from src.config import celery_app
from celery import group
from src.utils.decorators import singleton


@singleton
class FileProcessor:
    """
    File processor class to handle document processing.
    """

    @staticmethod
    def process_files(document_ids: str | List[str]) -> str | List[str] | None:
        """
        Start processing a document using Celery.

        Args:
            document_id: The ID of the document to process
            with_qa_generation: Whether to automatically queue QA generation after processing

        Returns:
            The task ID if the task was successfully queued, None otherwise
        """
        try:
            if isinstance(document_ids, list):
                job = group(
                    celery_app.signature(
                        "tasks.process_document",
                        args=[doc_id],
                        queue="document_processing",
                    )
                    for doc_id in document_ids
                )
                task = job.apply_async()
            else:
                task = celery_app.send_task(
                    "tasks.process_document",
                    args=[document_ids],
                    queue="document_processing",
                )
            return task.id
        except Exception:
            return None
