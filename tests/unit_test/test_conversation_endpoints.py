"""
Unit tests for conversation endpoints.
"""

import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4


@pytest.mark.unit
@pytest.mark.conversation
class TestConversationEndpoints:
    """Test conversation endpoints."""

    @pytest.mark.asyncio
    async def test_list_conversations(self, async_client, auth_headers):
        """Test listing conversations for a user."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch(
                "src.api.conversation.conversation_service.list_conversation"
            ) as mock_list,
        ):
            user_id = uuid4()
            mock_user.return_value = MagicMock(id=user_id)
            mock_list.return_value = []

            response = await async_client.get(
                "/conversation/list",
                headers=auth_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_create_conversation_success(self, async_client, auth_headers):
        """Test creating a new conversation."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch(
                "src.api.conversation.conversation_service.create_conversation"
            ) as mock_create,
        ):
            user_id = uuid4()
            mock_user.return_value = MagicMock(id=user_id)

            conv_id = uuid4()
            mock_conversation = MagicMock()
            mock_conversation.id = conv_id
            mock_conversation.app_name = "test_app"
            mock_conversation.title = "New Conversation"

            mock_create.return_value = mock_conversation

            response = await async_client.post(
                "/conversation/create?app_name=test_app",
                headers=auth_headers,
            )

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_messages(self, async_client, auth_headers):
        """Test listing messages for a conversation."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch(
                "src.api.conversation.conversation_service.list_messages"
            ) as mock_list,
        ):
            mock_user.return_value = MagicMock()
            mock_list.return_value = []

            conv_id = uuid4()
            response = await async_client.get(
                f"/message/list?conversation_id={conv_id}",
                headers=auth_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_delete_conversation_success(self, async_client, auth_headers):
        """Test deleting a conversation."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch(
                "src.api.conversation.conversation_service.delete_conversation"
            ) as mock_delete,
        ):
            user_id = uuid4()
            mock_user.return_value = MagicMock(id=user_id)
            mock_delete.return_value = None

            conv_id = uuid4()
            response = await async_client.delete(
                f"/conversation/delete?conversation_id={conv_id}",
                headers=auth_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert "deleted successfully" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_update_conversation_success(self, async_client, auth_headers):
        """Test updating a conversation."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch(
                "src.api.conversation.conversation_service.update_conversation_metadata"
            ) as mock_update,
        ):
            user_id = uuid4()
            mock_user.return_value = MagicMock(id=user_id)

            conv_id = uuid4()
            mock_conversation = MagicMock()
            mock_conversation.id = conv_id
            mock_conversation.title = "Updated Title"

            mock_update.return_value = mock_conversation

            response = await async_client.patch(
                "/conversation/update",
                headers=auth_headers,
                json={
                    "conversation_id": str(conv_id),
                    "title": "Updated Title",
                },
            )

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_research_status(self, async_client, auth_headers):
        """Test getting research status for a conversation."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch(
                "src.api.conversation.execution_manager.get_execution"
            ) as mock_get_exec,
        ):
            mock_user.return_value = MagicMock()
            mock_get_exec.return_value = None

            conv_id = str(uuid4())
            response = await async_client.get(
                f"/{conv_id}/status",
                headers=auth_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert "is_running" in data
            assert data["is_running"] is False

    @pytest.mark.asyncio
    async def test_get_research_status_running(self, async_client, auth_headers):
        """Test getting research status when research is running."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch(
                "src.api.conversation.execution_manager.get_execution"
            ) as mock_get_exec,
        ):
            mock_user.return_value = MagicMock()

            from datetime import datetime

            mock_execution = MagicMock()
            mock_execution.current_node = "research_subgraph_node"
            mock_execution.started_at = datetime.now()

            mock_get_exec.return_value = mock_execution

            conv_id = str(uuid4())
            response = await async_client.get(
                f"/{conv_id}/status",
                headers=auth_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["is_running"] is True
            assert data["can_skip"] is True

    @pytest.mark.asyncio
    async def test_skip_research_success(self, async_client, auth_headers):
        """Test skipping research."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch("src.api.conversation.execution_manager.skip_research") as mock_skip,
        ):
            mock_user.return_value = MagicMock()
            mock_skip.return_value = True

            conv_id = str(uuid4())
            response = await async_client.post(
                f"/{conv_id}/skip",
                headers=auth_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_skip_research_not_found(self, async_client, auth_headers):
        """Test skipping research when no research is running."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch("src.api.conversation.execution_manager.skip_research") as mock_skip,
        ):
            mock_user.return_value = MagicMock()
            mock_skip.return_value = False

            conv_id = str(uuid4())
            response = await async_client.post(
                f"/{conv_id}/skip",
                headers=auth_headers,
            )

            assert response.status_code >= 400

    @pytest.mark.asyncio
    async def test_list_conversations_unauthorized(self, async_client):
        """Test listing conversations without authentication."""
        response = await async_client.get("/conversation/list")

        assert response.status_code in [401, 403]
