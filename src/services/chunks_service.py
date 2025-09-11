from typing import List
from fastapi import HTTPException
from langchain_core.documents import Document
from src.rag.vector import vector_retrieval
from src.rag.vector import vector_storage
from src.utils.reference import normalize_ref
from src.utils.decorators import singleton


@singleton
class ChunksService:
    async def get_chunk_by_id(self, chunk_id: str) -> Document:
        """Retrieve a single chunk by its ID."""
        documents = await vector_retrieval.retrieve_by_ids([chunk_id])
        return documents[0]

    async def get_chunks_by_ids(self, chunk_ids: List[str]) -> List[Document]:
        """
        Retrieve multiple chunks by their IDs and group them by document.

        Args:
            chunk_ids: A list of chunk IDs to retrieve.

        Returns:
            A list of documents with their chunks grouped together.
        """
        if not chunk_ids:
            raise HTTPException(status_code=400, detail="Chunk IDs are required")

        documents = await vector_retrieval.retrieve_by_ids(chunk_ids)
        formatted_documents = normalize_ref(documents)

        return formatted_documents

    async def get_chunks_by_doc_id(self, doc_id: str) -> List[Document]:
        """Get chunks by document ID.

        Args:
            doc_id (str): The document ID to search for

        Returns:
            List[Document]: List of Document objects for the document
        """
        return await vector_storage.get_chunks_by_doc_id(doc_id=doc_id)

    async def get_chunk_ids_by_doc_id(self, doc_id: str) -> List[str]:
        """Get chunk IDs by document ID.

        Args:
            doc_id (str): The document ID to search for

        Returns:
            List[str]: List of chunk IDs for the document
        """
        return await vector_storage.get_chunk_ids_by_doc_id(doc_id=doc_id)
