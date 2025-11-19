"""
End-to-End tests for complete user journeys.
"""

from io import BytesIO
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.requires_db
@pytest.mark.requires_redis
class TestCompleteUserJourney:
    """Test complete end-to-end user scenarios."""

    @pytest.mark.asyncio
    async def test_new_user_complete_journey(self, async_client):
        """
        Test complete journey: Register -> Login -> Create KB -> Upload Doc ->
        Chat with Doc -> Logout
        """
        with (
            patch("src.api.auth.auth_service.register_user") as mock_register,
            patch("src.api.auth.auth_service.authenticate_user") as mock_login,
            patch("src.dependencies.auth.get_current_user") as mock_get_user,
            patch(
                "src.api.knowledge_base.kb_service.create_knowledge_base"
            ) as mock_create_kb,
            patch(
                "src.api.document.document_service.upload_and_process_document"
            ) as mock_upload,
            patch(
                "src.api.document.document_service.get_document_status"
            ) as mock_status,
            patch(
                "src.api.conversation.conversation_service.create_conversation"
            ) as mock_create_conv,
            patch("src.api.chat.chat_service.ask") as mock_ask,
            patch("src.api.auth.auth_service.logout_user") as mock_logout,
        ):
            user_id = uuid4()
            user_email = "e2e@example.com"

            # Step 1: Register
            mock_user_obj = MagicMock()
            mock_user_obj.model_dump.return_value = {
                "id": str(user_id),
                "email": user_email,
                "username": "e2euser",
                "role": "user",
            }
            mock_register.return_value = mock_user_obj

            register_response = await async_client.post(
                "/auth/register",
                json={
                    "email": user_email,
                    "username": "e2euser",
                    "password": "E2EPass123!",
                    "full_name": "E2E User",
                },
            )

            assert register_response.status_code == 200

            # Step 2: Login
            login_user = MagicMock()
            login_user.id = user_id
            login_user.email = user_email
            login_user.username = "e2euser"
            login_user.full_name = "E2E User"
            login_user.avatar_url = None
            login_user.auth_provider = "local"
            login_user.role = MagicMock(value="user")
            login_user.status = MagicMock(value="active")
            login_user.email_verified = True
            login_user.created_at = None
            login_user.last_login_at = None

            mock_token = MagicMock()
            mock_token.model_dump.return_value = {
                "access_token": "e2e-token",
                "refresh_token": "e2e-refresh",
                "token_type": "bearer",
            }

            mock_login.return_value = (login_user, mock_token)
            mock_get_user.return_value = login_user

            login_response = await async_client.post(
                "/auth/login",
                json={
                    "email": user_email,
                    "password": "E2EPass123!",
                },
            )

            assert login_response.status_code == 200
            token = login_response.json()["data"]["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            # Step 3: Create Knowledge Base
            kb_id = uuid4()
            mock_kb = MagicMock()
            mock_kb.id = kb_id
            mock_kb.name = "My First KB"
            mock_create_kb.return_value = mock_kb

            kb_response = await async_client.post(
                "/kb/create",
                headers=headers,
                json={
                    "name": "My First KB",
                    "description": "Knowledge base for testing",
                },
            )

            assert kb_response.status_code == 200

            # Step 4: Upload Document
            doc_id = uuid4()
            mock_doc = MagicMock()
            mock_doc.id = doc_id
            mock_doc.filename = "company_policy.pdf"
            mock_doc.original_filename = "company_policy.pdf"

            mock_upload.return_value = (mock_doc, "task-e2e-1")

            files = {
                "file": (
                    "company_policy.pdf",
                    BytesIO(b"PDF content here"),
                    "application/pdf",
                )
            }
            upload_response = await async_client.post(
                f"/documents/upload_and_process?knowledge_base_id={kb_id}",
                headers=headers,
                files=files,
            )

            assert upload_response.status_code == 200

            # Step 5: Check Document Status
            mock_status_obj = MagicMock()
            mock_status_obj.id = doc_id
            mock_status_obj.status = "FINISHED"
            mock_status_obj.progress = 100
            mock_status.return_value = mock_status_obj

            status_response = await async_client.get(
                f"/documents/{doc_id}/status",
                headers=headers,
            )

            assert status_response.status_code == 200

            # Step 6: Create Conversation
            conv_id = uuid4()
            mock_conv = MagicMock()
            mock_conv.id = conv_id
            mock_conv.app_name = "rag_app"
            mock_create_conv.return_value = mock_conv

            conv_response = await async_client.post(
                "/conversation/create?app_name=rag_app",
                headers=headers,
            )

            assert conv_response.status_code == 200

            # Step 7: Ask Question
            mock_response = MagicMock()
            mock_response.role = "assistant"
            mock_response.parts = [
                {"type": "text", "text": "Based on the policy document..."}
            ]
            mock_ask.return_value = mock_response

            chat_response = await async_client.post(
                "/chat/ask",
                headers=headers,
                json={
                    "message": {
                        "role": "user",
                        "parts": [
                            {"type": "text", "text": "What is the vacation policy?"}
                        ],
                        "metadata": {
                            "conversation_id": str(conv_id),
                            "kb_id": str(kb_id),
                        },
                    },
                    "agentic": False,
                },
            )

            assert chat_response.status_code == 200

            # Step 8: Logout
            mock_logout.return_value = True

            logout_response = await async_client.post(
                "/auth/logout",
                json={"refresh_token": "e2e-refresh"},
            )

            assert logout_response.status_code == 200

    @pytest.mark.asyncio
    async def test_collaborative_knowledge_sharing(self, async_client):
        """
        Test scenario: Admin creates KB, user uploads docs, both query KB.
        """
        with (
            patch("src.api.auth.auth_service.authenticate_user") as mock_login,
            patch("src.dependencies.auth.get_current_user") as mock_get_user,
            patch(
                "src.api.knowledge_base.kb_service.create_knowledge_base"
            ) as mock_create_kb,
            patch(
                "src.api.document.document_service.upload_and_process_document"
            ) as mock_upload,
            patch(
                "src.api.knowledge_base.kb_service.query_knowledge_base"
            ) as mock_query,
        ):
            # Admin login
            admin_id = uuid4()
            admin_user = MagicMock()
            admin_user.id = admin_id
            admin_user.email = "admin@example.com"
            admin_user.username = "admin"
            admin_user.full_name = "Admin User"
            admin_user.avatar_url = None
            admin_user.auth_provider = "local"
            admin_user.role = MagicMock(value="admin")

            admin_token = MagicMock()
            admin_token.model_dump.return_value = {
                "access_token": "admin-token",
                "refresh_token": "admin-refresh",
                "token_type": "bearer",
            }

            mock_login.return_value = (admin_user, admin_token)
            mock_get_user.return_value = admin_user

            admin_login_response = await async_client.post(
                "/auth/login",
                json={
                    "email": "admin@example.com",
                    "password": "AdminPass123!",
                },
            )

            assert admin_login_response.status_code == 200
            admin_headers = {"Authorization": "Bearer admin-token"}

            # Admin creates KB
            kb_id = uuid4()
            mock_kb = MagicMock()
            mock_kb.id = kb_id
            mock_kb.name = "Shared KB"
            mock_create_kb.return_value = mock_kb

            kb_response = await async_client.post(
                "/kb/create",
                headers=admin_headers,
                json={
                    "name": "Shared KB",
                    "description": "Collaborative knowledge base",
                },
            )

            assert kb_response.status_code == 200

            # Regular user login
            user_id = uuid4()
            regular_user = MagicMock()
            regular_user.id = user_id
            regular_user.email = "user@example.com"
            regular_user.username = "regularuser"
            regular_user.full_name = "Regular User"
            regular_user.avatar_url = None
            regular_user.auth_provider = "local"

            user_token = MagicMock()
            user_token.model_dump.return_value = {
                "access_token": "user-token",
                "refresh_token": "user-refresh",
                "token_type": "bearer",
            }

            mock_login.return_value = (regular_user, user_token)
            mock_get_user.return_value = regular_user

            user_login_response = await async_client.post(
                "/auth/login",
                json={
                    "email": "user@example.com",
                    "password": "UserPass123!",
                },
            )

            assert user_login_response.status_code == 200
            user_headers = {"Authorization": "Bearer user-token"}

            # User uploads document
            doc_id = uuid4()
            mock_doc = MagicMock()
            mock_doc.id = doc_id
            mock_doc.filename = "user_doc.pdf"
            mock_upload.return_value = (mock_doc, "task-collab-1")

            files = {"file": ("user_doc.pdf", BytesIO(b"content"), "application/pdf")}
            upload_response = await async_client.post(
                f"/documents/upload_and_process?knowledge_base_id={kb_id}",
                headers=user_headers,
                files=files,
            )

            assert upload_response.status_code == 200

            # Both query KB
            mock_query.return_value = [MagicMock(page_content="Shared knowledge")]

            # Admin query
            admin_query_response = await async_client.post(
                f"/kb/{kb_id}/query?query=shared+info",
                headers=admin_headers,
            )

            assert admin_query_response.status_code == 200

            # User query
            user_query_response = await async_client.post(
                f"/kb/{kb_id}/query?query=shared+info",
                headers=user_headers,
            )

            assert user_query_response.status_code == 200

    @pytest.mark.asyncio
    async def test_document_processing_with_websocket_tracking(self, async_client):
        """
        Test uploading document and tracking status via WebSocket info endpoint.
        """
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch(
                "src.api.document.document_service.upload_and_process_document"
            ) as mock_upload,
        ):
            user_id = uuid4()
            mock_user.return_value = MagicMock(id=user_id)

            headers = {"Authorization": "Bearer test-token"}
            kb_id = uuid4()

            # Upload document
            doc_id = uuid4()
            mock_doc = MagicMock()
            mock_doc.id = doc_id
            mock_doc.filename = "large_doc.pdf"
            mock_upload.return_value = (mock_doc, "task-ws-1")

            files = {
                "file": ("large_doc.pdf", BytesIO(b"large content"), "application/pdf")
            }
            upload_response = await async_client.post(
                f"/documents/upload_and_process?knowledge_base_id={kb_id}",
                headers=headers,
                files=files,
            )

            assert upload_response.status_code == 200

            # Get WebSocket info
            ws_info_response = await async_client.get(
                f"/websocket/document_status/{doc_id}/info",
                headers=headers,
            )

            assert ws_info_response.status_code == 200
            ws_data = ws_info_response.json()
            assert "websocket_url" in ws_data
            assert str(doc_id) in ws_data["websocket_url"]
