# src/rag/graph/custom_reranker.py
from typing import override

from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient

from src.rag.rerankers import get_reranker

reranker = get_reranker()


class CustomRerankerClient(OpenAIRerankerClient):
    @override
    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        reranked_indices = await reranker.rerank(query=query, documents=passages)
        return [(passages[index], score) for index, score in reranked_indices]
