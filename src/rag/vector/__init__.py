#src/rag/vector/__init__.py
from .storage import VectorStorage
from .retrieval import VectorRetrieval
from .migrations import VectorStorageMigration

vector_storage = VectorStorage()
vector_storage_migration = VectorStorageMigration(client=vector_storage.client)
vector_retrieval = VectorRetrieval(vector_store=vector_storage)