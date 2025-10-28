# src/db/repository/__init__.py
"""
Database Repository Module

This module provides repository classes for database operations.
Use the UnifiedRepository for a single interface to all database operations.
"""

from .knowledge_base import KnowledgeBaseRepository
from .document import DocumentRepository
from .qa import QARepository
from .conversation import ConversationRepository


__all__ = [
    "KnowledgeBaseRepository",
    "DocumentRepository",
    "QARepository",
    "ConversationRepository",
]
