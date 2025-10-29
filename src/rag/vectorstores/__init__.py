# src/rag/vectorstores/__init__.py
from src.rag.vectorstores.storage import VectorStorage
from src.rag.vectorstores.retrieval import VectorRetrieval
from src.rag.vectorstores.migrations import VectorStorageMigration

vector_storage = VectorStorage()
vector_storage_migration = VectorStorageMigration(client=vector_storage.client)
vector_retrieval = VectorRetrieval(vector_store=vector_storage)
