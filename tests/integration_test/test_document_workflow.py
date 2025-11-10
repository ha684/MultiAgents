"""
Integration tests for document management workflows.
"""

import pytest
from unittest.mock import patch, MagicMock
from uuid import uuid4
from io import BytesIO


@pytest.mark.integration
@pytest.mark.document
@pytest.mark.requires_db
class TestDocumentWorkflow:
    """Test complete document management workflows."""

    @pytest.mark.asyncio
    async def test_complete_document_upload_and_query_flow(
        self, async_client, auth_headers
    ):
        """Test uploading document and querying its content."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch(
                "src.api.knowledge_base.kb_service.create_knowledge_base"
            ) as mock_create_kb,
            patch(
                "src.api.document.document_service.upload_and_process_document"
            ) as mock_upload,
            patch(
                "src.api.document.document_service.get_document_status"
            ) as mock_status,
            patch("src.api.document.document_service.get_document") as mock_get_doc,
        ):
            user_id = uuid4()
            mock_user.return_value = MagicMock(id=user_id)

            # Step 1: Create knowledge base
            kb_id = uuid4()
            mock_kb = MagicMock()
            mock_kb.id = kb_id
            mock_kb.name = "Test KB"
            mock_create_kb.return_value = mock_kb

            kb_response = await async_client.post(
                "/kb/create",
                headers=auth_headers,
                json={
                    "name": "Test KB",
                    "description": "For testing",
                },
            )

            assert kb_response.status_code == 200

            # Step 2: Upload document
            doc_id = uuid4()
            mock_doc = MagicMock()
            mock_doc.id = doc_id
            mock_doc.filename = "test.pdf"
            mock_doc.original_filename = "test.pdf"

            mock_upload.return_value = (mock_doc, "task-123")

            files = {"file": ("test.pdf", BytesIO(b"test content"), "application/pdf")}
            upload_response = await async_client.post(
                f"/documents/upload_and_process?knowledge_base_id={kb_id}",
                headers=auth_headers,
                files=files,
            )

            assert upload_response.status_code == 200
            upload_data = upload_response.json()
            assert "task_id" in upload_data

            # Step 3: Check document status
            mock_status_obj = MagicMock()
            mock_status_obj.id = doc_id
            mock_status_obj.status = "FINISHED"
            mock_status_obj.progress = 100
            mock_status.return_value = mock_status_obj

            status_response = await async_client.get(
                f"/documents/{doc_id}/status",
                headers=auth_headers,
            )

            assert status_response.status_code == 200

            # Step 4: Get document details
            mock_doc.status = "FINISHED"
            mock_get_doc.return_value = mock_doc

            doc_response = await async_client.get(
                f"/documents/{doc_id}",
                headers=auth_headers,
            )

            assert doc_response.status_code == 200

    @pytest.mark.asyncio
    async def test_document_lifecycle_workflow(self, async_client, auth_headers):
        """Test complete document lifecycle: upload, process, deactivate, delete."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch(
                "src.api.document.document_service.upload_and_process_document"
            ) as mock_upload,
            patch(
                "src.api.document.document_service.toggle_document_active"
            ) as mock_toggle,
            patch("src.api.document.document_service.delete_document") as mock_delete,
        ):
            user_id = uuid4()
            mock_user.return_value = MagicMock(id=user_id)

            kb_id = uuid4()
            doc_id = uuid4()

            # Step 1: Upload document
            mock_doc = MagicMock()
            mock_doc.id = doc_id
            mock_doc.filename = "lifecycle.pdf"
            mock_doc.original_filename = "lifecycle.pdf"
            mock_doc.is_active = True

            mock_upload.return_value = (mock_doc, "task-456")

            files = {"file": ("lifecycle.pdf", BytesIO(b"content"), "application/pdf")}
            upload_response = await async_client.post(
                f"/documents/upload_and_process?knowledge_base_id={kb_id}",
                headers=auth_headers,
                files=files,
            )

            assert upload_response.status_code == 200

            # Step 2: Deactivate document
            mock_doc.is_active = False
            mock_toggle.return_value = mock_doc

            deactivate_response = await async_client.patch(
                f"/documents/{doc_id}/active?active=false",
                headers=auth_headers,
            )

            assert deactivate_response.status_code == 200

            # Step 3: Delete document
            mock_delete.return_value = None

            delete_response = await async_client.delete(
                f"/documents/{doc_id}",
                headers=auth_headers,
            )

            assert delete_response.status_code == 200

    @pytest.mark.asyncio
    async def test_document_qa_and_chunks_workflow(self, async_client, auth_headers):
        """Test accessing document Q&A and chunks."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch("src.api.document.document_service.get_document_qa_pairs") as mock_qa,
            patch("src.api.chunks.chunks_service.get_chunks_by_doc_id") as mock_chunks,
            patch(
                "src.api.chunks.chunks_service.get_chunk_ids_by_doc_id"
            ) as mock_chunk_ids,
        ):
            mock_user.return_value = MagicMock()

            doc_id = uuid4()

            # Step 1: Get Q&A pairs
            mock_qa.return_value = [
                MagicMock(question="Q1", answer="A1"),
                MagicMock(question="Q2", answer="A2"),
            ]

            qa_response = await async_client.get(
                f"/documents/{doc_id}/qa",
                headers=auth_headers,
            )

            assert qa_response.status_code == 200

            # Step 2: Get chunk IDs
            mock_chunk_ids.return_value = ["chunk-1", "chunk-2", "chunk-3"]

            chunk_ids_response = await async_client.get(
                f"/chunks/ids?document_id={doc_id}",
                headers=auth_headers,
            )

            assert chunk_ids_response.status_code == 200
            chunk_ids = chunk_ids_response.json()
            assert len(chunk_ids) == 3

            # Step 3: Get full chunks
            mock_chunks.return_value = [
                MagicMock(page_content="chunk 1", metadata={}),
                MagicMock(page_content="chunk 2", metadata={}),
            ]

            chunks_response = await async_client.get(
                f"/chunks/?document_id={doc_id}",
                headers=auth_headers,
            )

            assert chunks_response.status_code == 200

    @pytest.mark.asyncio
    async def test_multi_document_status_check(self, async_client, auth_headers):
        """Test checking status of multiple documents."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch(
                "src.api.document.document_service.get_multiple_document_status"
            ) as mock_multi_status,
        ):
            mock_user.return_value = MagicMock()

            doc_ids = [uuid4(), uuid4(), uuid4()]

            mock_statuses = [
                MagicMock(id=doc_ids[0], status="FINISHED"),
                MagicMock(id=doc_ids[1], status="PROCESSING"),
                MagicMock(id=doc_ids[2], status="PENDING"),
            ]
            mock_multi_status.return_value = mock_statuses

            response = await async_client.post(
                "/documents/status",
                headers=auth_headers,
                json=[str(doc_id) for doc_id in doc_ids],
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 3
