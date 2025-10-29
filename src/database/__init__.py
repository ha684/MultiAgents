# src/database/__init__.py
from src.database.repositories.conversation_repository import ConversationRepository
from src.database.repositories.document_repository import DocumentRepository
from src.database.repositories.knowledge_base_repository import KnowledgeBaseRepository
from src.database.repositories.qa_repository import QARepository

document_repository = DocumentRepository()
knowledge_base_repository = KnowledgeBaseRepository()
qa_repository = QARepository()
conversation_repository = ConversationRepository()
