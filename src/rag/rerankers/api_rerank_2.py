# src/rag/rerankers/api_rerank_2.py

import httpx
from pydantic.type_adapter import TypeAdapter

from src.core.config.settings import settings
from src.rag.rerankers.base import BaseReranker, Rank


class InferenceAPIReranker2(BaseReranker):
    def __init__(self, api_key: str, api_url: str):
        self.api_key = api_key
        self.api_url = api_url

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    async def rerank(
        self, query: str, documents: list[str], limit: int = 32
    ) -> list[Rank]:
        scored_document: list[Rank] = []
        for idx in range(0, len(documents), limit):
            batch = documents[idx : idx + limit]
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    url=self.api_url,
                    headers=self._headers,
                    json={
                        "query": query,
                        "documents": batch,
                        "return_documents": True,
                        "model": settings.rerank_model,
                    },
                    timeout=60.0,
                )
                response.raise_for_status()
                data = response.json().get("results", [])
                data = [
                    Rank(score=item.get("relevance_score"), index=item.get("index"))
                    for item in data
                ]
                ta = TypeAdapter(list[Rank])
                data = ta.validate_python(data)
                scored_document.extend(data)

        reranked_documents = sorted(
            scored_document, key=lambda x: x.score, reverse=True
        )

        return reranked_documents
