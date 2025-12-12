"""
Unit tests for chat endpoints.
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.dependencies.auth import get_current_user
from src.domain.schemas.chat import Message, TextPart
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
def mock_endpoint_protection():
    """Mock the endpoint_protection decorator to bypass queue management in unit tests."""

    # Since decorator is applied at import time, we need to patch the protector's protect_request method
    async def mock_protect_request(self, handler_func, *args, **kwargs):
        return await handler_func(*args, **kwargs)

    with patch(
        "src.middlewares.endpoint_manager.EndpointProtector.protect_request",
        mock_protect_request,
    ):
        yield


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
@pytest.mark.chat
class TestChatEndpoints:
    """Test chat endpoints."""

    @pytest.mark.asyncio
    async def test_ask_success(self, async_client, unit_auth_headers):
        """Test successful chat ask request."""
        with patch("src.api.chat.chat_service.ask") as mock_ask:
            # Create a proper Message object instead of MagicMock
            mock_response = Message(
                role="agent",
                parts=[TextPart(type="text", text="This is a response")],
            )
            mock_ask.return_value = mock_response

            response = await async_client.post(
                "/chat/ask",
                headers=unit_auth_headers,
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
            # Response is wrapped by ResponseHandlerMiddleware
            assert response.json()["success"] is True
            assert response.json()["data"]["role"] == "agent"
            assert len(response.json()["data"]["parts"]) == 1
            assert response.json()["data"]["parts"][0]["text"] == "This is a response"

    @pytest.mark.asyncio
    async def test_ask_empty_message(self, async_client, unit_auth_headers):
        """Test chat ask with empty message."""
        response = await async_client.post(
            "/chat/ask",
            headers=unit_auth_headers,
            json={
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": ""}],
                    "metadata": {},
                },
            },
        )
        assert response.status_code == 400
        assert "Message is required" in response.json()["error"]["detail"]["message"]

    @pytest.mark.asyncio
    async def test_ask_message_too_long(self, async_client, unit_auth_headers):
        """Test chat ask with message exceeding length limit."""
        long_message = "x" * 30001

        response = await async_client.post(
            "/chat/ask",
            headers=unit_auth_headers,
            json={
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": long_message}],
                    "metadata": {},
                },
            },
        )

        assert response.status_code == 400
        assert "too long" in response.json()["error"]["detail"]["message"].lower()

    @pytest.mark.asyncio
    async def test_ask_sse_success(self, async_client, unit_auth_headers):
        """Test successful SSE streaming chat request."""
        with patch("src.api.chat.chat_service.ask_sse") as mock_ask_sse:

            async def mock_stream():
                yield b"data: event1\n\n"
                yield b"data: event2\n\n"

            mock_ask_sse.return_value = mock_stream()

            response = await async_client.post(
                "/chat/ask/sse",
                headers=unit_auth_headers,
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
    async def test_ask_sse_empty_message(self, async_client, unit_auth_headers):
        """Test SSE streaming with empty message."""
        response = await async_client.post(
            "/chat/ask/sse",
            headers=unit_auth_headers,
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
        # Temporarily remove the dependency override for this test
        app.dependency_overrides.clear()

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
    async def test_ask_with_knowledge_base(self, async_client, unit_auth_headers):
        """Test chat ask with knowledge base context."""
        with patch("src.api.chat.chat_service.ask") as mock_ask:
            # Create a proper Message object instead of MagicMock
            mock_response = Message(
                role="agent",
                parts=[TextPart(type="text", text="Response with KB context")],
            )
            mock_ask.return_value = mock_response

            response = await async_client.post(
                "/chat/ask",
                headers=unit_auth_headers,
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
            # Response is wrapped by ResponseHandlerMiddleware
            assert response.json()["success"] is True
            assert response.json()["data"]["role"] == "agent"
            assert (
                response.json()["data"]["parts"][0]["text"]
                == "Response with KB context"
            )
