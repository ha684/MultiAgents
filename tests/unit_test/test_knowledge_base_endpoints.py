"""
Unit tests for knowledge base endpoints.
"""

import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4


@pytest.mark.unit
@pytest.mark.knowledge_base
class TestKnowledgeBaseEndpoints:
    """Test knowledge base endpoints."""

    @pytest.mark.asyncio
    async def test_create_knowledge_base_success(self, async_client, auth_headers):
        """Test successful knowledge base creation."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch(
                "src.api.knowledge_base.kb_service.create_knowledge_base"
            ) as mock_create,
        ):
            mock_user.return_value = MagicMock(id=uuid4())

            kb_id = uuid4()
            mock_kb = MagicMock()
            mock_kb.id = kb_id
            mock_kb.name = "Test KB"
            mock_kb.description = "Test Description"

            mock_create.return_value = mock_kb

            response = await async_client.post(
                "/kb/create",
                headers=auth_headers,
                json={
                    "name": "Test KB",
                    "description": "Test Description",
                },
            )

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_knowledge_bases_for_user(self, async_client, auth_headers):
        """Test listing knowledge bases for a user."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch(
                "src.api.knowledge_base.kb_service.list_knowledge_bases"
            ) as mock_list,
        ):
            user_id = uuid4()
            mock_user.return_value = MagicMock(id=user_id)

            mock_response = MagicMock()
            mock_response.knowledge_bases = []
            mock_response.total = 0

            mock_list.return_value = mock_response

            response = await async_client.post(
                "/kb/user",
                headers=auth_headers,
                json={"skip": 0, "limit": 10},
            )

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_knowledge_bases_for_admin(
        self, async_client, admin_auth_headers
    ):
        """Test listing all knowledge bases (admin)."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch(
                "src.api.knowledge_base.kb_service.list_knowledge_bases_all"
            ) as mock_list,
        ):
            mock_user.return_value = MagicMock(id=uuid4(), role="admin")

            mock_response = MagicMock()
            mock_response.knowledge_bases = []
            mock_response.total = 0

            mock_list.return_value = mock_response

            response = await async_client.get(
                "/kb/admin?limit=10&skip=0",
                headers=admin_auth_headers,
            )

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_knowledge_base_by_id(self, async_client, auth_headers):
        """Test retrieving a knowledge base by ID."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch(
                "src.api.knowledge_base.kb_service.get_knowledge_base_by_id"
            ) as mock_get,
        ):
            user_id = uuid4()
            mock_user.return_value = MagicMock(id=user_id)

            kb_id = str(uuid4())
            mock_kb = MagicMock()
            mock_kb.id = kb_id
            mock_kb.name = "Test KB"

            mock_get.return_value = mock_kb

            response = await async_client.get(
                f"/kb/{kb_id}",
                headers=auth_headers,
            )

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_knowledge_base_not_found(self, async_client, auth_headers):
        """Test retrieving non-existent knowledge base."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch(
                "src.api.knowledge_base.kb_service.get_knowledge_base_by_id"
            ) as mock_get,
        ):
            mock_user.return_value = MagicMock(id=uuid4())
            mock_get.side_effect = Exception("Knowledge base not found")

            kb_id = str(uuid4())
            response = await async_client.get(
                f"/kb/{kb_id}",
                headers=auth_headers,
            )

            assert response.status_code >= 400

    @pytest.mark.asyncio
    async def test_query_knowledge_base(self, async_client, auth_headers):
        """Test querying a knowledge base."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch(
                "src.api.knowledge_base.kb_service.query_knowledge_base"
            ) as mock_query,
        ):
            mock_user.return_value = MagicMock()
            mock_query.return_value = []

            kb_id = str(uuid4())
            response = await async_client.post(
                f"/kb/{kb_id}/query?query=test+query",
                headers=auth_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_delete_knowledge_base_success(self, async_client, auth_headers):
        """Test deleting a knowledge base."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch(
                "src.api.knowledge_base.kb_service.delete_knowledge_base"
            ) as mock_delete,
        ):
            user_id = uuid4()
            mock_user.return_value = MagicMock(id=user_id)
            mock_delete.return_value = {
                "message": "Knowledge base deleted successfully"
            }

            kb_id = str(uuid4())
            response = await async_client.delete(
                f"/kb/{kb_id}",
                headers=auth_headers,
            )

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_knowledge_base_success(self, async_client, auth_headers):
        """Test updating a knowledge base."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch(
                "src.api.knowledge_base.kb_service.update_knowledge_base"
            ) as mock_update,
        ):
            user_id = uuid4()
            mock_user.return_value = MagicMock(id=user_id)

            kb_id = str(uuid4())
            mock_kb = MagicMock()
            mock_kb.id = kb_id
            mock_kb.name = "Updated KB"
            mock_kb.description = "Updated Description"
            mock_kb.is_active = True

            mock_update.return_value = mock_kb

            response = await async_client.put(
                f"/kb/{kb_id}/update",
                headers=auth_headers,
                json={
                    "kb_id": kb_id,
                    "name": "Updated KB",
                    "description": "Updated Description",
                    "is_active": True,
                },
            )

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_qa_pairs_by_kb_id(self, async_client, auth_headers):
        """Test retrieving Q&A pairs for a knowledge base."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch("src.api.knowledge_base.kb_service.get_qa_pairs_by_kb_id") as mock_qa,
        ):
            mock_user.return_value = MagicMock()
            mock_qa.return_value = []

            kb_id = uuid4()
            response = await async_client.get(
                f"/kb/{kb_id}/qa?limit=25",
                headers=auth_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_create_knowledge_base_unauthorized(self, async_client):
        """Test creating knowledge base without authentication."""
        response = await async_client.post(
            "/kb/create",
            json={
                "name": "Test KB",
                "description": "Test Description",
            },
        )

        assert response.status_code in [401, 403]
