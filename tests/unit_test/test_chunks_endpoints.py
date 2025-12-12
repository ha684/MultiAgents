"""
Unit tests for chunks endpoints.
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.dependencies.auth import get_current_user
from src.main import app


@pytest.fixture
def unit_auth_headers():
    """Provide mock authentication headers for unit tests (no DB access)."""
    return {"Authorization": "Bearer mock_test_token"}


@pytest.fixture
def mock_current_user():
    """Create a mock user for unit tests (no DB access)."""
    mock_user = MagicMock()
    mock_user.id = uuid4()
    mock_user.email = "test@example.com"
    mock_user.role = "user"
    return mock_user


@pytest.fixture(autouse=True)
def override_dependencies(mock_current_user):
    """Override FastAPI dependencies for unit tests."""

    async def mock_get_current_user():
        return mock_current_user

    # Store original dependency
    original_dependency = app.dependency_overrides.copy()

    # Override the dependency
    app.dependency_overrides[get_current_user] = mock_get_current_user

    yield

    # Restore original dependencies
    app.dependency_overrides = original_dependency


@pytest.mark.unit
@pytest.mark.chunks
class TestChunksEndpoints:
    """Test chunks endpoints."""

    @pytest.mark.asyncio
    async def test_get_chunks_by_document_id(self, async_client, unit_auth_headers):
        """Test retrieving chunks for a document."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch("src.api.chunks.chunks_service.get_chunks_by_doc_id") as mock_get,
        ):
            mock_user.return_value = MagicMock()
            mock_get.return_value = []

            doc_id = str(uuid4())
            response = await async_client.get(
                f"/chunks/?document_id={doc_id}",
                headers=unit_auth_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_get_chunk_ids_by_document_id(self, async_client, unit_auth_headers):
        """Test retrieving chunk IDs for a document."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch("src.api.chunks.chunks_service.get_chunk_ids_by_doc_id") as mock_get,
        ):
            mock_user.return_value = MagicMock()
            mock_get.return_value = ["chunk-1", "chunk-2", "chunk-3"]

            doc_id = str(uuid4())
            response = await async_client.get(
                f"/chunks/ids?document_id={doc_id}",
                headers=unit_auth_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 3

    @pytest.mark.asyncio
    async def test_get_chunks_by_ids(self, async_client, unit_auth_headers):
        """Test retrieving multiple chunks by their IDs."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch("src.api.chunks.chunks_service.get_chunks_by_ids") as mock_get,
        ):
            mock_user.return_value = MagicMock()
            mock_get.return_value = []

            chunk_ids = ["chunk-1", "chunk-2"]
            response = await async_client.post(
                "/chunks/batch",
                headers=unit_auth_headers,
                json={"chunk_ids": chunk_ids},
            )

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_get_chunk_by_id(self, async_client, unit_auth_headers):
        """Test retrieving a single chunk by ID."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch("src.api.chunks.chunks_service.get_chunk_by_id") as mock_get,
        ):
            mock_user.return_value = MagicMock()

            mock_chunk = MagicMock()
            mock_chunk.page_content = "Test chunk content"
            mock_chunk.metadata = {"doc_id": "test-doc"}

            mock_get.return_value = mock_chunk

            chunk_id = "test-chunk-id"
            response = await async_client.get(
                f"/chunks/{chunk_id}",
                headers=unit_auth_headers,
            )

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_chunk_not_found(self, async_client, unit_auth_headers):
        """Test retrieving non-existent chunk."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch("src.api.chunks.chunks_service.get_chunk_by_id") as mock_get,
        ):
            mock_user.return_value = MagicMock()
            mock_get.side_effect = Exception("Chunk not found")

            chunk_id = "non-existent-chunk"
            response = await async_client.get(
                f"/chunks/{chunk_id}",
                headers=unit_auth_headers,
            )

            assert response.status_code >= 400

    @pytest.mark.asyncio
    async def test_get_chunks_unauthorized(self, async_client):
        """Test retrieving chunks without authentication."""
        doc_id = str(uuid4())
        response = await async_client.get(f"/chunks/?document_id={doc_id}")

        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_get_chunks_empty_result(self, async_client, unit_auth_headers):
        """Test retrieving chunks for document with no chunks."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch("src.api.chunks.chunks_service.get_chunks_by_doc_id") as mock_get,
        ):
            mock_user.return_value = MagicMock()
            mock_get.return_value = []

            doc_id = str(uuid4())
            response = await async_client.get(
                f"/chunks/?document_id={doc_id}",
                headers=unit_auth_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data == []
