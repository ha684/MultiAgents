# src/database/repositories/__init__.py
"""
Database Repository Module

This module provides repository classes for database operations.
Use the UnifiedRepository for a single interface to all database operations.
"""

from src.database.repositories.conversation_repository import ConversationRepository
from src.database.repositories.document_repository import DocumentRepository
from src.database.repositories.knowledge_base_repository import KnowledgeBaseRepository
from src.database.repositories.qa_repository import QARepository

__all__ = [
    "KnowledgeBaseRepository",
    "DocumentRepository",
    "QARepository",
    "ConversationRepository",
]
