"""
Integration tests for knowledge base workflows.
"""

import pytest
from unittest.mock import patch, MagicMock
from uuid import uuid4
from io import BytesIO


@pytest.mark.integration
@pytest.mark.knowledge_base
@pytest.mark.requires_db
class TestKnowledgeBaseWorkflow:
    """Test complete knowledge base workflows."""

    @pytest.mark.asyncio
    async def test_kb_creation_and_document_upload_workflow(
        self, async_client, auth_headers
    ):
        """Test creating KB and uploading multiple documents."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch(
                "src.api.knowledge_base.kb_service.create_knowledge_base"
            ) as mock_create_kb,
            patch(
                "src.api.document.document_service.upload_and_process_document"
            ) as mock_upload,
            patch("src.api.document.document_service.list_documents") as mock_list,
        ):
            user_id = uuid4()
            mock_user.return_value = MagicMock(id=user_id)

            # Step 1: Create knowledge base
            kb_id = uuid4()
            mock_kb = MagicMock()
            mock_kb.id = kb_id
            mock_kb.name = "My KB"
            mock_kb.description = "Test KB"

            mock_create_kb.return_value = mock_kb

            kb_response = await async_client.post(
                "/kb/create",
                headers=auth_headers,
                json={
                    "name": "My KB",
                    "description": "Test KB",
                },
            )

            assert kb_response.status_code == 200

            # Step 2: Upload multiple documents
            doc_ids = []
            for i in range(3):
                doc_id = uuid4()
                doc_ids.append(doc_id)

                mock_doc = MagicMock()
                mock_doc.id = doc_id
                mock_doc.filename = f"doc_{i}.pdf"
                mock_doc.original_filename = f"doc_{i}.pdf"

                mock_upload.return_value = (mock_doc, f"task-{i}")

                files = {
                    "file": (f"doc_{i}.pdf", BytesIO(b"content"), "application/pdf")
                }
                upload_response = await async_client.post(
                    f"/documents/upload_and_process?knowledge_base_id={kb_id}",
                    headers=auth_headers,
                    files=files,
                )

                assert upload_response.status_code == 200

            # Step 3: List all documents in KB
            mock_list_response = MagicMock()
            mock_list_response.documents = [MagicMock() for _ in range(3)]
            mock_list_response.total = 3
            mock_list.return_value = mock_list_response

            list_response = await async_client.get(
                f"/documents?knowledge_base_id={kb_id}&skip=0&limit=10",
                headers=auth_headers,
            )

            assert list_response.status_code == 200

    @pytest.mark.asyncio
    async def test_kb_query_and_chat_workflow(self, async_client, auth_headers):
        """Test querying KB and using it for chat."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch(
                "src.api.knowledge_base.kb_service.get_knowledge_base_by_id"
            ) as mock_get_kb,
            patch(
                "src.api.knowledge_base.kb_service.query_knowledge_base"
            ) as mock_query,
            patch(
                "src.api.conversation.conversation_service.create_conversation"
            ) as mock_create_conv,
            patch("src.api.chat.chat_service.ask") as mock_ask,
        ):
            user_id = uuid4()
            mock_user.return_value = MagicMock(id=user_id)

            kb_id = str(uuid4())

            # Step 1: Get KB details
            mock_kb = MagicMock()
            mock_kb.id = kb_id
            mock_kb.name = "Test KB"
            mock_get_kb.return_value = mock_kb

            kb_response = await async_client.get(
                f"/kb/{kb_id}",
                headers=auth_headers,
            )

            assert kb_response.status_code == 200

            # Step 2: Query KB
            mock_query.return_value = [
                MagicMock(page_content="Relevant content 1"),
                MagicMock(page_content="Relevant content 2"),
            ]

            query_response = await async_client.post(
                f"/kb/{kb_id}/query?query=test+query",
                headers=auth_headers,
            )

            assert query_response.status_code == 200

            # Step 3: Create conversation
            conv_id = uuid4()
            mock_conv = MagicMock()
            mock_conv.id = conv_id
            mock_create_conv.return_value = mock_conv

            conv_response = await async_client.post(
                "/conversation/create?app_name=test_app",
                headers=auth_headers,
            )

            assert conv_response.status_code == 200

            # Step 4: Ask question with KB context
            mock_response = MagicMock()
            mock_response.role = "assistant"
            mock_response.parts = [{"type": "text", "text": "Answer based on KB"}]
            mock_ask.return_value = mock_response

            chat_response = await async_client.post(
                "/chat/ask",
                headers=auth_headers,
                json={
                    "message": {
                        "role": "user",
                        "parts": [{"type": "text", "text": "What is in the KB?"}],
                        "metadata": {
                            "conversation_id": str(conv_id),
                            "kb_id": kb_id,
                        },
                    },
                    "agentic": False,
                },
            )

            assert chat_response.status_code == 200

    @pytest.mark.asyncio
    async def test_kb_update_and_delete_workflow(self, async_client, auth_headers):
        """Test updating and deleting knowledge base."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch(
                "src.api.knowledge_base.kb_service.create_knowledge_base"
            ) as mock_create,
            patch(
                "src.api.knowledge_base.kb_service.update_knowledge_base"
            ) as mock_update,
            patch(
                "src.api.knowledge_base.kb_service.delete_knowledge_base"
            ) as mock_delete,
        ):
            user_id = uuid4()
            mock_user.return_value = MagicMock(id=user_id)

            # Step 1: Create KB
            kb_id = str(uuid4())
            mock_kb = MagicMock()
            mock_kb.id = kb_id
            mock_kb.name = "Original KB"
            mock_kb.is_active = True
            mock_create.return_value = mock_kb

            create_response = await async_client.post(
                "/kb/create",
                headers=auth_headers,
                json={
                    "name": "Original KB",
                    "description": "Original",
                },
            )

            assert create_response.status_code == 200

            # Step 2: Update KB
            mock_kb.name = "Updated KB"
            mock_kb.description = "Updated"
            mock_update.return_value = mock_kb

            update_response = await async_client.put(
                f"/kb/{kb_id}/update",
                headers=auth_headers,
                json={
                    "kb_id": kb_id,
                    "name": "Updated KB",
                    "description": "Updated",
                    "is_active": True,
                },
            )

            assert update_response.status_code == 200

            # Step 3: Delete KB
            mock_delete.return_value = {"message": "Deleted successfully"}

            delete_response = await async_client.delete(
                f"/kb/{kb_id}",
                headers=auth_headers,
            )

            assert delete_response.status_code == 200

    @pytest.mark.asyncio
    async def test_kb_qa_pairs_workflow(self, async_client, auth_headers):
        """Test getting Q&A pairs from knowledge base."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_user,
            patch("src.api.knowledge_base.kb_service.get_qa_pairs_by_kb_id") as mock_qa,
        ):
            mock_user.return_value = MagicMock()

            kb_id = uuid4()

            mock_qa_pairs = [
                MagicMock(question="Q1", answer="A1", document_id=uuid4()),
                MagicMock(question="Q2", answer="A2", document_id=uuid4()),
                MagicMock(question="Q3", answer="A3", document_id=uuid4()),
            ]
            mock_qa.return_value = mock_qa_pairs

            response = await async_client.get(
                f"/kb/{kb_id}/qa?limit=25",
                headers=auth_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
