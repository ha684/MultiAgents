# src/rag/rerankers/base.py
from abc import ABC, abstractmethod
from typing import List, Sequence

from pydantic import BaseModel


class Rank(BaseModel):
    """Model to represent the reranked documents."""

    score: float
    index: int

    class ConfigDict:
        from_attributes = True


class BaseReranker(ABC):
    """Base class for reranking models.

    This class defines the interface for reranking models, which should implement
    the `rerank` method to reorder a list of documents based on a query.
    """

    @abstractmethod
    async def rerank(self, query: str, documents: List[str]) -> Sequence[Rank]:
        """Reorders documents based on the given query.

        Args:
            query (str): The query string to use for reranking.
            documents (List[dict]): A list of documents to be reranked.

        Returns:
            List[dict]: The reranked list of documents.
        """
        raise NotImplementedError("Rerank method must be implemented by subclasses.")
