# src/api/__init__.py

"""
API module for KMS Service.
This module provides API schemas and services for the KMS service.
"""

from src.api.auth import router as auth_router
from src.api.chat import router as chat_router
from src.api.chunks import router as chunks_router
from src.api.conversation import router as conversation_router
from src.api.document import router as document_router
from src.api.knowledge_base import router as knowledge_base_router
from src.api.streaming_chat import router as streaming_chat_router
from src.api.websocket import router as websocket_router

ROUTERS = [
    auth_router,
    document_router,
    knowledge_base_router,
    chat_router,
    streaming_chat_router,
    chunks_router,
    websocket_router,
    conversation_router,
]
