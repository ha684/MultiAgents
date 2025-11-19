"""
Unit tests for chat endpoints.
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
@pytest.mark.chat
class TestChatEndpoints:
    """Test chat endpoints."""

    @pytest.mark.asyncio
    async def test_ask_success(self, async_client, auth_headers):
        """Test successful chat ask request."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch("src.api.chat.chat_service.ask") as mock_ask,
        ):
            mock_user.return_value = MagicMock()

            mock_response = MagicMock()
            mock_response.role = "assistant"
            mock_response.parts = [{"type": "text", "text": "This is a response"}]
            mock_ask.return_value = mock_response

            response = await async_client.post(
                "/chat/ask",
                headers=auth_headers,
                json={
                    "message": {
                        "role": "user",
                        "parts": [{"type": "text", "text": "What is AI?"}],
                        "metadata": {
                            "conversation_id": "test-conv-id",
                            "kb_id": "test-kb-id",
                        },
                    },
                    "agentic": False,
                    "web_search": False,
                },
            )

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_ask_empty_message(self, async_client, auth_headers):
        """Test chat ask with empty message."""
        with patch("src.dependencies.auth.get_current_user") as mock_user:
            mock_user.return_value = MagicMock()

            response = await async_client.post(
                "/chat/ask",
                headers=auth_headers,
                json={
                    "message": {
                        "role": "user",
                        "parts": [{"type": "text", "text": ""}],
                        "metadata": {},
                    },
                },
            )

            assert response.status_code == 400
            assert "Message is required" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_ask_message_too_long(self, async_client, auth_headers):
        """Test chat ask with message exceeding length limit."""
        with patch("src.dependencies.auth.get_current_user") as mock_user:
            mock_user.return_value = MagicMock()

            long_message = "x" * 30001

            response = await async_client.post(
                "/chat/ask",
                headers=auth_headers,
                json={
                    "message": {
                        "role": "user",
                        "parts": [{"type": "text", "text": long_message}],
                        "metadata": {},
                    },
                },
            )

            assert response.status_code == 400
            assert "too long" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_ask_sse_success(self, async_client, auth_headers):
        """Test successful SSE streaming chat request."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch("src.api.chat.chat_service.ask_sse") as mock_ask_sse,
        ):
            mock_user.return_value = MagicMock()

            async def mock_stream():
                yield b"data: event1\n\n"
                yield b"data: event2\n\n"

            mock_ask_sse.return_value = mock_stream()

            response = await async_client.post(
                "/chat/ask/sse",
                headers=auth_headers,
                json={
                    "message": {
                        "role": "user",
                        "parts": [{"type": "text", "text": "Tell me about AI"}],
                        "metadata": {
                            "conversation_id": "test-conv-id",
                        },
                    },
                    "agentic": True,
                },
            )

            assert response.status_code == 200
            assert (
                response.headers["content-type"] == "text/event-stream; charset=utf-8"
            )

    @pytest.mark.asyncio
    async def test_ask_sse_empty_message(self, async_client, auth_headers):
        """Test SSE streaming with empty message."""
        with patch("src.dependencies.auth.get_current_user") as mock_user:
            mock_user.return_value = MagicMock()

            response = await async_client.post(
                "/chat/ask/sse",
                headers=auth_headers,
                json={
                    "message": {
                        "role": "user",
                        "parts": [{"type": "text", "text": ""}],
                        "metadata": {},
                    },
                },
            )

            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_ask_unauthorized(self, async_client):
        """Test chat ask without authentication."""
        response = await async_client.post(
            "/chat/ask",
            json={
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": "What is AI?"}],
                    "metadata": {},
                },
            },
        )

        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_ask_with_knowledge_base(self, async_client, auth_headers):
        """Test chat ask with knowledge base context."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch("src.api.chat.chat_service.ask") as mock_ask,
        ):
            mock_user.return_value = MagicMock()

            mock_response = MagicMock()
            mock_response.role = "assistant"
            mock_response.parts = [{"type": "text", "text": "Response with KB context"}]
            mock_ask.return_value = mock_response

            response = await async_client.post(
                "/chat/ask",
                headers=auth_headers,
                json={
                    "message": {
                        "role": "user",
                        "parts": [
                            {"type": "text", "text": "What does the document say?"}
                        ],
                        "metadata": {
                            "conversation_id": "test-conv-id",
                            "kb_id": "test-kb-id",
                        },
                    },
                    "agentic": False,
                    "web_search": False,
                },
            )

            assert response.status_code == 200
