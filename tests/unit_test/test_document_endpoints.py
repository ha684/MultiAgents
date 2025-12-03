"""
Unit tests for document endpoints.
"""

from io import BytesIO
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


@pytest.mark.unit
@pytest.mark.document
class TestDocumentEndpoints:
    """Test document endpoints."""

    @pytest.mark.asyncio
    async def test_upload_document_success(self, async_client, auth_headers):
        """Test successful document upload."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch(
                "src.api.document.document_service.upload_and_process_document"
            ) as mock_upload,
        ):
            mock_user.return_value = MagicMock(id=uuid4())

            doc_id = uuid4()
            mock_doc = MagicMock()
            mock_doc.id = doc_id
            mock_doc.filename = "test.pdf"
            mock_doc.original_filename = "test.pdf"

            mock_upload.return_value = (mock_doc, "task-123")

            kb_id = str(uuid4())
            files = {"file": ("test.pdf", BytesIO(b"test content"), "application/pdf")}

            response = await async_client.post(
                f"/documents/upload_and_process?knowledge_base_id={kb_id}",
                headers=auth_headers,
                files=files,
            )

            assert response.status_code == 200
            data = response.json()
            assert "id" in data
            assert "task_id" in data
            assert data["filename"] == "test.pdf"

    @pytest.mark.asyncio
    async def test_upload_document_too_large(self, async_client, auth_headers):
        """Test uploading document that exceeds size limit."""
        with patch("src.dependencies.auth.get_current_user") as mock_user:
            mock_user.return_value = MagicMock(id=uuid4())

            kb_id = str(uuid4())
            # Simulate large file by mocking content-length header
            large_file = BytesIO(b"x" * (101 * 1024 * 1024))  # 101MB
            files = {"file": ("large.pdf", large_file, "application/pdf")}

            # Note: This test may need adjustment based on actual implementation
            response = await async_client.post(
                f"/documents/upload_and_process?knowledge_base_id={kb_id}",
                headers={**auth_headers, "content-length": str(101 * 1024 * 1024)},
                files=files,
            )

            # Should fail with 413 or similar
            assert response.status_code in [413, 400]

    @pytest.mark.asyncio
    async def test_get_document_success(self, async_client, auth_headers):
        """Test retrieving document details."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch("src.api.document.document_service.get_document") as mock_get,
        ):
            mock_user.return_value = MagicMock()

            doc_id = uuid4()
            mock_doc = MagicMock()
            mock_doc.id = doc_id
            mock_doc.filename = "test.pdf"
            mock_doc.status = "FINISHED"

            mock_get.return_value = mock_doc

            response = await async_client.get(
                f"/documents/{doc_id}",
                headers=auth_headers,
            )

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_document_not_found(self, async_client, auth_headers):
        """Test retrieving non-existent document."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch("src.api.document.document_service.get_document") as mock_get,
        ):
            mock_user.return_value = MagicMock()
            mock_get.side_effect = Exception("Document not found")

            doc_id = uuid4()
            response = await async_client.get(
                f"/documents/{doc_id}",
                headers=auth_headers,
            )

            assert response.status_code >= 400

    @pytest.mark.asyncio
    async def test_get_document_status(self, async_client, auth_headers):
        """Test getting document processing status."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch(
                "src.api.document.document_service.get_document_status"
            ) as mock_status,
        ):
            mock_user.return_value = MagicMock()

            doc_id = uuid4()
            mock_status_obj = MagicMock()
            mock_status_obj.id = doc_id
            mock_status_obj.status = "PROCESSING"
            mock_status_obj.progress = 50

            mock_status.return_value = mock_status_obj

            response = await async_client.get(
                f"/documents/{doc_id}/status",
                headers=auth_headers,
            )

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_documents(self, async_client, auth_headers):
        """Test listing documents in a knowledge base."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch("src.api.document.document_service.list_documents") as mock_list,
        ):
            mock_user.return_value = MagicMock()

            kb_id = uuid4()
            mock_response = MagicMock()
            mock_response.documents = []
            mock_response.total = 0
            mock_response.skip = 0
            mock_response.limit = 10

            mock_list.return_value = mock_response

            response = await async_client.get(
                f"/documents?knowledge_base_id={kb_id}&skip=0&limit=10",
                headers=auth_headers,
            )

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_document_success(self, async_client, auth_headers):
        """Test deleting a document."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch("src.api.document.document_service.delete_document") as mock_delete,
        ):
            mock_user.return_value = MagicMock()
            mock_delete.return_value = None

            doc_id = uuid4()
            response = await async_client.delete(
                f"/documents/{doc_id}",
                headers=auth_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert "deleted successfully" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_toggle_document_active(self, async_client, auth_headers):
        """Test activating/deactivating a document."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch(
                "src.api.document.document_service.toggle_document_active"
            ) as mock_toggle,
        ):
            mock_user.return_value = MagicMock()

            doc_id = uuid4()
            mock_doc = MagicMock()
            mock_doc.id = doc_id
            mock_doc.is_active = False

            mock_toggle.return_value = mock_doc

            response = await async_client.patch(
                f"/documents/{doc_id}/active?active=false",
                headers=auth_headers,
            )

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_document_qa_pairs(self, async_client, auth_headers):
        """Test retrieving Q&A pairs for a document."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch("src.api.document.document_service.get_document_qa_pairs") as mock_qa,
        ):
            mock_user.return_value = MagicMock()
            mock_qa.return_value = []

            doc_id = uuid4()
            response = await async_client.get(
                f"/documents/{doc_id}/qa",
                headers=auth_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_get_related_documents(self, async_client, auth_headers):
        """Test retrieving related documents."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch(
                "src.api.document.document_service.get_related_document_ids"
            ) as mock_related,
        ):
            mock_user.return_value = MagicMock()
            mock_related.return_value = []

            doc_id = str(uuid4())
            kb_id = str(uuid4())

            response = await async_client.post(
                f"/documents/{doc_id}/related",
                headers=auth_headers,
                json={"kb_id": kb_id},
                params={"kb_id": kb_id},
            )

            assert response.status_code == 200
            data = response.json()
            assert "related_documents" in data
