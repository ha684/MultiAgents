from langchain_qdrant import QdrantVectorStore, RetrievalMode
from typing import (
    Optional,
    Tuple,
    Any,
    override,
    Iterable,
    List,
    Sequence,
    AsyncGenerator,
)
from langchain_core.documents import Document
from qdrant_client import models
import uuid
from itertools import islice
from qdrant_client import AsyncQdrantClient


class CustomQdrantVectorStore(QdrantVectorStore):
    @property
    def client(self) -> AsyncQdrantClient:
        """Get the Qdrant client instance that is being used.

        Returns:
            QdrantClient: An instance of `QdrantClient`.
        """
        return self._client

    @override
    async def similarity_search_with_score(
        self,
        query: str,
        k: int = 4,
        filter: Optional[models.Filter] = None,
        search_params: Optional[models.SearchParams] = None,
        offset: int = 0,
        score_threshold: Optional[float] = None,
        consistency: Optional[models.ReadConsistency] = None,
        hybrid_fusion: Optional[models.FusionQuery] = None,
        **kwargs: Any,
    ) -> List[Tuple[Document, float]]:
        """Return docs most similar to query.

        Returns:
            List of documents most similar to the query text and distance for each.
        """
        query_options = {
            "collection_name": self.collection_name,
            "query_filter": filter,
            "search_params": search_params,
            "limit": k,
            "offset": offset,
            "with_payload": True,
            "with_vectors": False,
            "score_threshold": score_threshold,
            "consistency": consistency,
            **kwargs,
        }
        if self.retrieval_mode == RetrievalMode.DENSE:
            query_dense_embedding = await self.embeddings.embed_query(query)
            response = await self.client.query_points(
                query=query_dense_embedding,
                using=self.vector_name,
                **query_options,
            )
            results = response.points

        elif self.retrieval_mode == RetrievalMode.SPARSE:
            query_sparse_embedding = await self.sparse_embeddings.aembed_query(query)
            response = await self.client.query_points(
                query=models.SparseVector(
                    indices=query_sparse_embedding.indices,
                    values=query_sparse_embedding.values,
                ),
                using=self.sparse_vector_name,
                **query_options,
            )
            results = response.points

        elif self.retrieval_mode == RetrievalMode.HYBRID:
            query_dense_embedding = await self.embeddings.embed_query(query)
            query_sparse_embedding = await self.sparse_embeddings.aembed_query(query)
            response = await self.client.query_points(
                prefetch=[
                    models.Prefetch(
                        using=self.vector_name,
                        query=query_dense_embedding,
                        filter=filter,
                        limit=k,
                        params=search_params,
                    ),
                    models.Prefetch(
                        using=self.sparse_vector_name,
                        query=models.SparseVector(
                            indices=query_sparse_embedding.indices,
                            values=query_sparse_embedding.values,
                        ),
                        filter=filter,
                        limit=k,
                        params=search_params,
                    ),
                ],
                query=hybrid_fusion or models.FusionQuery(fusion=models.Fusion.RRF),
                **query_options,
            )
            results = response.points

        else:
            raise ValueError(f"Invalid retrieval mode. {self.retrieval_mode}.")
        return [
            (
                self._document_from_point(
                    result,
                    self.collection_name,
                    self.content_payload_key,
                    self.metadata_payload_key,
                ),
                result.score,
            )
            for result in results
        ]

    @override
    async def _build_vectors(
        self,
        texts: Iterable[str],
    ) -> List[models.VectorStruct]:
        if self.retrieval_mode == RetrievalMode.DENSE:
            batch_embeddings = await self.embeddings.embed_documents(list(texts))
            return [
                {
                    self.vector_name: vector,
                }
                for vector in batch_embeddings
            ]

        elif self.retrieval_mode == RetrievalMode.SPARSE:
            batch_sparse_embeddings = await self.sparse_embeddings.aembed_documents(
                list(texts)
            )
            return [
                {
                    self.sparse_vector_name: models.SparseVector(
                        values=vector.values, indices=vector.indices
                    )
                }
                for vector in batch_sparse_embeddings
            ]

        elif self.retrieval_mode == RetrievalMode.HYBRID:
            dense_embeddings = await self.embeddings.embed_documents(list(texts))
            sparse_embeddings = await self.sparse_embeddings.aembed_documents(
                list(texts)
            )

            assert len(dense_embeddings) == len(sparse_embeddings), (
                "Mismatched length between dense and sparse embeddings."
            )

            return [
                {
                    self.vector_name: dense_vector,
                    self.sparse_vector_name: models.SparseVector(
                        values=sparse_vector.values, indices=sparse_vector.indices
                    ),
                }
                for dense_vector, sparse_vector in zip(
                    dense_embeddings, sparse_embeddings
                )
            ]

        else:
            raise ValueError(
                f"Unknown retrieval mode. {self.retrieval_mode} to build vectors."
            )

    @override
    async def _generate_batches(
        self,
        texts: Iterable[str],
        metadatas: Optional[List[dict]] = None,
        ids: Optional[Sequence[str | int]] = None,
        batch_size: int = 64,
    ) -> AsyncGenerator[tuple[list[str | int], list[models.PointStruct]], Any]:
        texts_iterator = iter(texts)
        metadatas_iterator = iter(metadatas or [])
        ids_iterator = iter(ids or [uuid.uuid4().hex for _ in iter(texts)])

        while batch_texts := list(islice(texts_iterator, batch_size)):
            batch_metadatas = list(islice(metadatas_iterator, batch_size)) or None
            batch_ids = list(islice(ids_iterator, batch_size))

            payloads = self._build_payloads(
                batch_texts,
                batch_metadatas,
                self.content_payload_key,
                self.metadata_payload_key,
            )

            vectors = await self._build_vectors(batch_texts)

            points = [
                models.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload,
                )
                for point_id, vector, payload in zip(
                    batch_ids,
                    vectors,
                    payloads,
                )
            ]
            yield batch_ids, points

    @override
    async def add_texts(
        self,
        texts: Iterable[str],
        metadatas: Optional[List[dict]] = None,
        ids: Optional[Sequence[str | int]] = None,
        batch_size: int = 64,
        **kwargs: Any,
    ) -> List[str | int]:
        """Add texts with embeddings to the vectorstore.

        Returns:
            List of ids from adding the texts into the vectorstore.
        """
        added_ids = []
        async for batch_ids, points in self._generate_batches(
            texts, metadatas, ids, batch_size
        ):
            await self.client.upsert(
                collection_name=self.collection_name, points=points, **kwargs
            )
            added_ids.extend(batch_ids)

        return added_ids

    @override
    async def add_documents(
        self,
        documents: List[Document],
        **kwargs: Any,
    ) -> List[str | int]:
        if "ids" not in kwargs:
            ids = [doc.id for doc in documents]
            if any(ids):
                kwargs["ids"] = ids

        texts = [doc.page_content for doc in documents]
        metadatas = [doc.metadata for doc in documents]
        return await self.add_texts(texts, metadatas, **kwargs)

    @override
    async def delete(
        self,
        collection_name: str,
        ids: Optional[List[str | int]] = None,
        **kwargs: Any,
    ) -> Optional[bool]:
        """Delete documents by their ids.

        Args:
            ids: List of ids to delete.
            **kwargs: Other keyword arguments that subclasses might use.

        Returns:
            True if deletion is successful, False otherwise.
        """
        result = await self.client.delete(
            collection_name=collection_name,
            points_selector=ids,
        )
        return result.status == models.UpdateStatus.COMPLETED

    @override
    async def get_by_ids(self, ids: Sequence[str | int], /) -> List[Document]:
        results = await self.client.retrieve(
            collection_name=self.collection_name,
            ids=ids,
            with_payload=True,
        )
        return [
            self._document_from_point(
                result,
                self.collection_name,
                self.content_payload_key,
                self.metadata_payload_key,
            )
            for result in results
        ]
