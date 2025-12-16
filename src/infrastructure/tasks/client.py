# src/infrastructure/tasks/client.py
"""
Centralized Celery Task Client

This module provides a unified interface for queuing and managing Celery tasks.
It follows the singleton pattern and provides type-safe methods for different task types.
"""

import uuid
from typing import Any

from celery.result import AsyncResult

from src.core.config.celery_app import celery_app
from src.utils.logger_conf import logger


class TaskClient:
    """
    Centralized client for managing Celery tasks.

    Provides a clean interface for:
    - Document processing tasks
    - Chat inference tasks
    - QA generation tasks
    """

    def __init__(self):
        self.app = celery_app

    def process_document(self, document_id: str | uuid.UUID) -> str | None:
        """
        Queue a document for processing.

        Args:
            document_id: The ID of the document to process

        Returns:
            The task ID if successfully queued, None otherwise
        """
        try:
            doc_id_str = (
                str(document_id) if isinstance(document_id, uuid.UUID) else document_id
            )
            task = self.app.send_task(
                "tasks.process_document",
                args=[doc_id_str],
                queue="document_processing",
            )
            logger.info(
                f"Queued document processing task: {task.id} for document: {doc_id_str}"
            )
            return task.id
        except Exception as e:
            logger.error(f"Failed to queue document processing task: {e}")
            return None

    def process_documents_batch(self, document_ids: list[str | uuid.UUID]) -> list[str]:
        """
        Queue multiple documents for processing.

        Args:
            document_ids: List of document IDs to process

        Returns:
            List of task IDs for successfully queued tasks
        """
        task_ids = []
        for doc_id in document_ids:
            task_id = self.process_document(doc_id)
            if task_id:
                task_ids.append(task_id)
        return task_ids

    def queue_chat_inference(
        self,
        task_id: str,
        conversation_id: str | uuid.UUID,
        user_id: str,
        kb_id: str | uuid.UUID,
        message_text: str,
        message_metadata: dict[str, Any],
        agentic: bool = False,
        web_search_active: bool = False,
        web_search_config: dict[str, Any] | None = None,
    ) -> str | None:
        """
        Queue a chat inference task.

        Args:
            task_id: Pre-generated task ID for tracking
            conversation_id: The conversation ID
            user_id: The user ID
            kb_id: The knowledge base ID
            message_text: The user's message
            message_metadata: Additional metadata for the message
            agentic: Whether to use agentic workflow
            web_search_active: Whether web search is enabled
            web_search_config: Web search configuration

        Returns:
            The task ID if successfully queued, None otherwise
        """
        try:
            task = self.app.send_task(
                "tasks.chat_inference",
                args=[task_id],
                kwargs={
                    "conversation_id": str(conversation_id),
                    "user_id": user_id,
                    "kb_id": str(kb_id),
                    "message_text": message_text,
                    "message_metadata": message_metadata,
                    "agentic": agentic,
                    "web_search_active": web_search_active,
                    "web_search_config": web_search_config or {},
                },
                queue="chat_inference",
                task_id=task_id,
            )
            logger.info(f"Queued chat inference task: {task.id}")
            return task.id
        except Exception as e:
            logger.error(f"Failed to queue chat inference task: {e}")
            return None

    def queue_qa_generation(
        self,
        document_id: str | uuid.UUID,
        kb_id: str | uuid.UUID,
        full_text: str,
    ) -> str | None:
        """
        Queue QA pair generation for a document.

        Args:
            document_id: The document ID
            kb_id: The knowledge base ID
            full_text: The full text content

        Returns:
            The task ID if successfully queued, None otherwise
        """
        try:
            task = self.app.send_task(
                "tasks.generate_qa_pairs",
                args=[str(document_id), str(kb_id), full_text],
                queue="qa_generation",
            )
            logger.info(f"Queued QA generation task: {task.id}")
            return task.id
        except Exception as e:
            logger.error(f"Failed to queue QA generation task: {e}")
            return None

    def get_task_status(self, task_id: str) -> dict[str, Any]:
        """
        Get the status of a task.

        Args:
            task_id: The task ID

        Returns:
            Dictionary with task status information
        """
        try:
            result = AsyncResult(task_id, app=self.app)
            return {
                "task_id": task_id,
                "status": result.status,
                "ready": result.ready(),
                "successful": result.successful() if result.ready() else None,
                "result": result.result if result.ready() else None,
            }
        except Exception as e:
            logger.error(f"Failed to get task status: {e}")
            return {
                "task_id": task_id,
                "status": "UNKNOWN",
                "error": str(e),
            }

    def revoke_task(self, task_id: str, terminate: bool = False) -> bool:
        """
        Revoke/cancel a task.

        Args:
            task_id: The task ID to revoke
            terminate: Whether to terminate the task if it's running

        Returns:
            True if revocation was sent successfully
        """
        try:
            self.app.control.revoke(task_id, terminate=terminate)
            logger.info(f"Revoked task: {task_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to revoke task {task_id}: {e}")
            return False


task_client = TaskClient()
