from .repository.conversation import ConversationRepository
from .repository.document import DocumentRepository
from .repository.knowledge_base import KnowledgeBaseRepository
from .repository.qa import QARepository

document_repository = DocumentRepository()
knowledge_base_repository = KnowledgeBaseRepository()
qa_repository = QARepository()
conversation_repository = ConversationRepository()





