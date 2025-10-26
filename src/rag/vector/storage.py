from typing import List, Optional
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_qdrant import FastEmbedSparse, RetrievalMode
from qdrant_client import AsyncQdrantClient, models
from src.rag.embeding import embedding
from src.config.settings import settings
from src.utils.decorators import singleton
from .custom_qdrantvectorstore import CustomQdrantVectorStore
from src.utils.logger_conf import logger


@singleton
class VectorStorage:
    """
    A singleton class for managing vector storage.
    This class provides methods to store and retrieve vectors.
    """

    def __init__(self, embeddings: Optional[Embeddings] = None):
        embeddings = embeddings or embedding
        sparse_model_name = "Qdrant/bm42-all-minilm-l6-v2-attentions"
        sparse_embeddings = FastEmbedSparse(
            parallel=2,
            model_name=sparse_model_name,
        )

        client = AsyncQdrantClient(
            url=settings.vector_storage_url,
        )

        self.storage = CustomQdrantVectorStore(
            client=client,
            collection_name=settings.vector_collection_name,
            embedding=embeddings,
            sparse_embedding=sparse_embeddings,
            retrieval_mode=RetrievalMode.HYBRID,
            vector_name="dense",
            sparse_vector_name="sparse",
            validate_collection_config=False,
        )

    @property
    def client(self) -> AsyncQdrantClient:
        return self.storage.client

    async def add_chunks(self, chunks: List[Document]) -> List[str]:
        if not chunks:
            return []

        return await self.storage.add_documents(chunks)

    async def update_chunks_status(
        self,
        ids: List[str],
        active: bool,
        vector_collection_name: str = settings.vector_collection_name,
    ) -> models.UpdateResult:
        """
        Update the status of document chunks in the vector storage.
        Args:
            ids (List[str]): List of document chunk IDs to update.
            active (bool): The new status to set for the chunks.
        Returns:
            List[str]: List of updated document chunk IDs.
        """
        return await self.storage.client.set_payload(
            collection_name=vector_collection_name,
            points=models.PointIdsList(points=[*ids]),
            payload={"inactive": not active},
        )

    async def update_chunks_status_by_doc_id(
        self,
        doc_id: str,
        active: bool,
        vector_collection_name: str = settings.vector_collection_name,
    ) -> models.UpdateResult:
        """
        Update the status of document chunks in the vector storage by document ID.
        Args:
            kb_id (str): The knowledge base ID to filter chunks.
            active (bool): The new status to set for the chunks.
        Returns:
            models.UpdateResult: Result of the update operation.
        """
        return await self.storage.client.set_payload(
            collection_name=vector_collection_name,
            points=models.Filter(
                must=[
                    models.FieldCondition(
                        key="metadata.document_id",
                        match=models.MatchValue(value=doc_id),
                    )
                ]
            ),
            payload={"inactive": not active},
        )

    async def delete_chunks(
        self,
        vector_collection_name: str = settings.vector_collection_name,
        ids: Optional[List[str]] = None,
    ) -> bool | None:
        """
        Delete document chunks from the vector storage.
        Args:
            ids (List[str]): List of document chunk IDs to delete.
        Returns:
            models.DeleteResult: Result of the delete operation.
        """
        return await self.storage.delete(
            collection_name=vector_collection_name, ids=[*ids]
        )

    async def delete_chunks_by_doc_id(
        self, doc_id: str, vector_collection_name: str = settings.vector_collection_name
    ) -> models.UpdateResult:
        """
        Delete document chunks from the vector storage by document ID.
        Args:
            kb_id (str): The knowledge base ID to filter chunks.
        Returns:
            models.DeleteResult: Result of the delete operation.
        """
        return await self.storage.client.delete(
            collection_name=vector_collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="metadata.document_id",
                            match=models.MatchValue(value=doc_id),
                        )
                    ]
                )
            ),
        )

    async def delete_chunks_by_kb_id(
        self, kb_id: str, vector_collection_name: str = settings.vector_collection_name
    ) -> models.UpdateResult:
        return await self.storage.client.delete(
            collection_name=vector_collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="metadata.kb_id",
                            match=models.MatchValue(value=str(kb_id)),
                        )
                    ]
                )
            ),
        )

    async def get_chunk_ids_by_doc_id(
        self,
        doc_id: str,
        vector_collection_name: str = settings.vector_collection_name,
        limit: int = 100,
    ) -> List[str]:
        """
        Get all chunk IDs for a specific document ID.

        Args:
            doc_id (str): The document ID to search for
            vector_collection_name (str): Collection name
            limit (int): Maximum number of chunks to retrieve

        Returns:
            List[str]: List of chunk IDs for the document
        """
        try:
            search_result = await self.storage.client.scroll(
                collection_name=vector_collection_name,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="metadata.document_id",
                            match=models.MatchValue(value=doc_id),
                        )
                    ]
                ),
                limit=limit,
                with_payload=False,
                with_vectors=False,
            )

            chunk_ids = [str(point.id) for point in search_result[0]]
            return chunk_ids

        except Exception as e:
            logger.error(f"Error retrieving chunk IDs for document {doc_id}: {e}")
            raise e

    async def get_chunks_by_doc_id(
        self,
        doc_id: str,
        vector_collection_name: str = settings.vector_collection_name,
        limit: int = 10000,
    ) -> List[Document]:
        """
        Get all chunks (as Document objects) for a specific document ID.

        Args:
            doc_id (str): The document ID to search for
            vector_collection_name (str): Collection name
            limit (int): Maximum number of chunks to retrieve

        Returns:
            List[Document]: List of Document objects for the document
        """
        try:
            chunk_ids = await self.get_chunk_ids_by_doc_id(
                doc_id, vector_collection_name, limit
            )

            if not chunk_ids:
                logger.warning(f"No chunks found for document {doc_id}")
                return []

            documents = await self.storage.get_by_ids(chunk_ids)
            return documents

        except Exception as e:
            logger.error(f"Error retrieving chunks for document {doc_id}: {e}")
            raise e
