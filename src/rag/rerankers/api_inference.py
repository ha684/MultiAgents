from typing import List
from pydantic.type_adapter import TypeAdapter
import httpx
from .base import BaseReranker, Rank


class InferenceAPIReranker(BaseReranker):
    def __init__(self, api_key: str, api_url: str):
        self.api_key = api_key
        self.api_url = api_url

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    async def rerank(
        self, query: str, documents: List[str], limit: int = 32
    ) -> List[Rank]:
        scored_documents = []

        for idx in range(0, len(documents), limit):
            batch = documents[idx : idx + limit]
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url=self.api_url,
                    headers=self._headers,
                    json={"query": query, "texts": batch},
                )
                response.raise_for_status()
                data = response.json()

                ta = TypeAdapter(List[Rank])
                batch_ranks = ta.validate_python(data)

                for rank in batch_ranks:
                    rank.index = idx + rank.index

                scored_documents.extend(batch_ranks)

        reranked_documents = sorted(
            scored_documents, key=lambda x: x.score, reverse=True
        )

        return reranked_documents
