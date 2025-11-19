# src/rag/vectorstores/retrieval.py
from copy import deepcopy
from typing import cast

from langchain_core.documents import Document
from qdrant_client import models

from src.rag.rerankers import get_reranker
from src.rag.vectorstores.storage import VectorStorage
from src.utils.logger_conf import logger


class VectorRetrieval:
    """
    A class to handle vector retrieval operations.
    """

    def __init__(self, vector_store: VectorStorage):
        """
        Initializes the VectorRetrieval with a vector store.

        Args:
            vector_store: An instance of a vector store to perform retrieval operations.
        """
        self.vector_store = vector_store
        self.reranker = get_reranker()

    async def compress_documents(
        self,
        documents: list[Document],
        query: str,
        top_n: int,
        with_scores: bool = False,
    ) -> list[Document]:
        if not documents:
            return []

        texts_to_rerank = [doc.page_content for doc in documents]

        try:
            ranks = await self.reranker.rerank(query=query, documents=texts_to_rerank)

            if len(ranks) != len(documents):
                raise ValueError(
                    f"Reranker returned {len(ranks)} ranks for {len(documents)} documents."
                )

            scored_documents = []
            for rank in ranks:
                original_doc_index = rank.index
                doc_copy = deepcopy(documents[original_doc_index])
                if not hasattr(doc_copy, "metadata") or doc_copy.metadata is None:
                    doc_copy.metadata = {}
                doc_copy.metadata["rerank_score"] = rank.score
                scored_documents.append((doc_copy, rank.score))

            scored_documents.sort(key=lambda x: x[1], reverse=True)

            # threshold = 0.6
            # # Filter out documents with scores below the threshold
            # scored_documents = [
            #     (doc, score) for doc, score in scored_documents if score >= threshold
            # ]

            # Return top_n documents
            if with_scores:
                compressed_docs = [
                    Document(
                        page_content=doc.page_content,
                        metadata={
                            **doc.metadata,
                            "rerank_score": score,
                        },
                    )
                    for doc, score in scored_documents[:top_n]
                ]
            else:
                compressed_docs = [doc for doc, _ in scored_documents[:top_n]]

            return compressed_docs

        except Exception:
            logger.exception("An unexpected error occurred during reranking")
            return documents

    async def retrieve(
        self,
        kb_id: str,
        query: str,
        top_k: int,
        top_n: int,
        filters: models.Filter | None = None,
    ) -> list[Document]:
        """
        Retrieves the top-k most similar vectors from the vector store.

        Args:
            kb_id: The knowledge base ID to filter the vectors.
            query_vector: The vector for which similar vectors are to be retrieved.
            top_k: The number of top similar vectors to return.
            filter: A filter to apply to the retrieval query.

        Returns:
            A list of the top-k similar vectors.
        """
        try:
            must_filters: list[models.Condition] = [
                models.FieldCondition(
                    key="metadata.kb_id", match=models.MatchValue(value=kb_id)
                ),
            ]
            if filters and filters.must:
                if not isinstance(filters.must, list):
                    must_filters.append(filters.must)
                else:
                    must_filters.extend(filters.must)

            should_filters: list[models.Condition] = []
            if filters and filters.should:
                if not isinstance(filters.should, list):
                    should_filters.append(filters.should)
                else:
                    should_filters.extend(filters.should)

            must_not_filters: list[models.Condition] = [
                models.FieldCondition(
                    key="inactive",
                    match=models.MatchValue(value=True),
                )
            ]
            if filters and filters.must_not:
                if not isinstance(filters.must_not, list):
                    must_not_filters.append(filters.must_not)
                else:
                    must_not_filters.extend(filters.must_not)

            docs_w_score = await self.vector_store.storage.similarity_search_with_score(
                query,
                k=top_k,
                filter=models.Filter(
                    must=must_filters,
                    should=should_filters,
                    must_not=must_not_filters,
                ),
            )

            docs = [
                Document(
                    page_content=doc.page_content,
                    metadata={
                        **doc.metadata,
                        "vector_score": score,
                    },
                )
                for doc, score in docs_w_score
            ]

            logger.info(f"Retrieve {len(docs)} documents from vector store")

            if not docs:
                return []

            if not top_n or top_n == 0:
                return docs
            else:
                compressed_docs = await self.compress_documents(
                    documents=docs, query=query, top_n=top_n, with_scores=True
                )
            logger.info(f"Retrieved {len(compressed_docs)} documents from reranker")
            return compressed_docs
        except Exception as e:
            logger.error("Error retrieving documents from vector store")
            raise e

    async def retrieve_by_ids(self, chunk_ids: list[str]) -> list[Document]:
        """
        Retrieves documents from the vector store by their chunk IDs.

        Args:
            chunk_ids: A list of chunk IDs to retrieve.

        Returns:
            A list of documents corresponding to the chunk IDs.
        """
        if not chunk_ids:
            logger.warning("No chunk IDs provided for retrieval.")
            return []
        try:
            docs = await self.vector_store.storage.get_by_ids(
                chunk_ids,
            )
            # Reorder documents to match the order of chunk_ids
            docs_dict: dict[str, Document] = {
                cast(str, doc.metadata.get("_id")): doc for doc in docs
            }
            docs = [
                docs_dict.get(chunk_id)
                for chunk_id in chunk_ids
                if chunk_id in docs_dict
            ]

            return cast(list[Document], docs) if docs else []
        except Exception as e:
            logger.error(f"Error retrieving documents by IDs {chunk_ids}: {e}")
            return []
