"""
Unit tests for WebSocket endpoints.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


@pytest.mark.unit
@pytest.mark.websocket
class TestWebSocketEndpoints:
    """Test WebSocket endpoints."""

    @pytest.mark.asyncio
    async def test_document_status_info_endpoint(self, async_client, auth_headers):
        """Test document status info endpoint."""
        with patch("src.dependencies.auth.get_current_user") as mock_user:
            mock_user.return_value = MagicMock()

            doc_id = uuid4()
            response = await async_client.get(
                f"/websocket/document_status/{doc_id}/info",
                headers=auth_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert "websocket_url" in data
            assert "description" in data
            assert str(doc_id) in data["websocket_url"]

    @pytest.mark.asyncio
    async def test_websocket_manager_connect(self):
        """Test WebSocketManager connect method."""
        from src.api.websocket import WebSocketManager

        mock_websocket = MagicMock()
        mock_websocket.accept = AsyncMock()

        doc_id = uuid4()
        ws_manager = WebSocketManager(mock_websocket, doc_id)

        result = await ws_manager.connect()

        assert result is True
        assert ws_manager.is_connected is True
        mock_websocket.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_websocket_manager_send_message(self):
        """Test WebSocketManager send_message method."""
        from src.api.websocket import WebSocketManager

        mock_websocket = MagicMock()
        mock_websocket.send_json = AsyncMock()

        doc_id = uuid4()
        ws_manager = WebSocketManager(mock_websocket, doc_id)
        ws_manager.is_connected = True

        result = await ws_manager.send_message(
            "test_type", data={"key": "value"}, message="Test message"
        )

        assert result is True
        mock_websocket.send_json.assert_called_once()
        call_args = mock_websocket.send_json.call_args[0][0]
        assert call_args["type"] == "test_type"
        assert call_args["data"] == {"key": "value"}
        assert call_args["message"] == "Test message"

    @pytest.mark.asyncio
    async def test_websocket_manager_send_message_not_connected(self):
        """Test send_message when not connected."""
        from src.api.websocket import WebSocketManager

        mock_websocket = MagicMock()

        doc_id = uuid4()
        ws_manager = WebSocketManager(mock_websocket, doc_id)
        ws_manager.is_connected = False

        result = await ws_manager.send_message("test_type")

        assert result is False

    @pytest.mark.asyncio
    async def test_websocket_manager_send_initial_status(self):
        """Test send_initial_status method."""
        from src.api.websocket import WebSocketManager

        mock_websocket = MagicMock()
        mock_websocket.send_json = AsyncMock()

        doc_id = uuid4()
        ws_manager = WebSocketManager(mock_websocket, doc_id)
        ws_manager.is_connected = True

        mock_status = MagicMock()
        mock_status.model_dump.return_value = {
            "id": str(doc_id),
            "status": "PROCESSING",
            "progress": 50,
        }

        with patch.object(
            ws_manager.document_service, "get_document_status"
        ) as mock_get_status:
            mock_get_status.return_value = mock_status

            result = await ws_manager.send_initial_status()

            assert result is True
            mock_get_status.assert_called_once_with(doc_id)

    @pytest.mark.asyncio
    async def test_websocket_manager_process_status_event(self):
        """Test process_status_event method."""
        from src.api.websocket import WebSocketManager

        mock_websocket = MagicMock()
        mock_websocket.send_json = AsyncMock()

        doc_id = uuid4()
        ws_manager = WebSocketManager(mock_websocket, doc_id)
        ws_manager.is_connected = True

        event = {
            "id": str(doc_id),
            "status": "PROCESSING",
            "progress": 75,
        }

        result = await ws_manager.process_status_event(event)

        assert result is True
        assert mock_websocket.send_json.call_count == 1

    @pytest.mark.asyncio
    async def test_websocket_manager_process_completed_event(self):
        """Test process_status_event with COMPLETED status."""
        from src.api.websocket import WebSocketManager

        mock_websocket = MagicMock()
        mock_websocket.send_json = AsyncMock()

        doc_id = uuid4()
        ws_manager = WebSocketManager(mock_websocket, doc_id)
        ws_manager.is_connected = True

        event = {
            "id": str(doc_id),
            "status": "COMPLETED",
        }

        result = await ws_manager.process_status_event(event)

        # Should return False to stop listening
        assert result is False
        # Should send status_update and complete messages
        assert mock_websocket.send_json.call_count == 2

    @pytest.mark.asyncio
    async def test_websocket_manager_disconnect(self):
        """Test disconnect method."""
        from src.api.websocket import WebSocketManager

        mock_websocket = MagicMock()
        mock_websocket.close = AsyncMock()

        doc_id = uuid4()
        ws_manager = WebSocketManager(mock_websocket, doc_id)
        ws_manager.is_connected = True

        await ws_manager.disconnect()

        assert ws_manager.is_connected is False
        mock_websocket.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_websocket_manager_process_wrong_document_event(self):
        """Test process_status_event with different document ID."""
        from src.api.websocket import WebSocketManager

        mock_websocket = MagicMock()
        mock_websocket.send_json = AsyncMock()

        doc_id = uuid4()
        other_doc_id = uuid4()
        ws_manager = WebSocketManager(mock_websocket, doc_id)
        ws_manager.is_connected = True

        event = {
            "id": str(other_doc_id),
            "status": "PROCESSING",
        }

        result = await ws_manager.process_status_event(event)

        # Should return True but not send message
        assert result is True
        mock_websocket.send_json.assert_not_called()
