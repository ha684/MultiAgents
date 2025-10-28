# src/db/__init__.py
from src.db.repository.conversation import ConversationRepository
from src.db.repository.document import DocumentRepository
from src.db.repository.knowledge_base import KnowledgeBaseRepository
from src.db.repository.qa import QARepository

document_repository = DocumentRepository()
knowledge_base_repository = KnowledgeBaseRepository()
qa_repository = QARepository()
conversation_repository = ConversationRepository()
