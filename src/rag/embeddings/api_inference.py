# src/rag/embeddings/api_inference.py
import asyncio
from typing import List

import httpx
from langchain_core.embeddings import Embeddings
from pydantic import BaseModel, ConfigDict

from src.utils.logger_conf import logger


class InferenceAPIEmbeddings(BaseModel, Embeddings):
    """Embed texts using the API.

    Requires a Inference API key and a model name.
    """

    model_config = ConfigDict(extra="allow", protected_namespaces=())

    api_key: str
    model_name: str
    api_url: str
    retries: int = 3
    batch_size: int = 32

    def __init__(
        self,
        api_key: str,
        model_name: str,
        api_url: str,
        retries: int = 3,
        batch_size: int = 32,
    ):
        """
        Args:
            api_key (str): The API key for authentication.
            model_name (str): The name of the model to use for embeddings.
            api_url (str): The URL of the API endpoint.
            retries (int): Number of retries for failed requests.
            batch_size (int): Number of texts to embed in a single request.
        """
        super().__init__(
            api_key=api_key,
            model_name=model_name,
            api_url=api_url,
            retries=retries,
            batch_size=batch_size,
        )

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embeds a batch of texts using a single API request with retry mechanism."""
        for attempt in range(self.retries + 1):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        self.api_url,
                        headers=self._headers,
                        json={"input": texts, "model": self.model_name},
                        timeout=30.0,
                    )
                    response.raise_for_status()

                    data = response.json()
                    embeddings = [e["embedding"] for e in data.get("data", [])]

                    if len(embeddings) != len(texts):
                        raise ValueError(
                            f"Expected {len(texts)} embeddings, got {len(embeddings)}"
                        )

                    return embeddings

            except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as e:
                if attempt < self.retries:
                    wait_time = 2**attempt
                    logger.warning(
                        f"Embedding request failed (attempt {attempt + 1}/{self.retries + 1}): {e}. Retrying in {wait_time} seconds..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.exception(
                        f"Error fetching embeddings after {self.retries + 1} attempts: {e}"
                    )
                    raise e

        return [[]] * len(texts)

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query text."""
        embeddings = await self.embed([text])
        return embeddings[0]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple documents in batches."""
        batch_size = self.batch_size
        all_embeddings = []

        tasks = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            tasks.append(self.embed(batch))

        batch_results = await asyncio.gather(*tasks)

        for batch_embeddings in batch_results:
            all_embeddings.extend(batch_embeddings)

        return all_embeddings


class RagasSyncEmbeddings(Embeddings):
    """
    Phiên bản đồng bộ (Synchronous) của InferenceAPIEmbeddings để dùng cho Ragas.
    """

    def __init__(
        self, api_url: str, api_key: str, model_name: str = "text-embedding-ada-002"
    ):
        self.api_url = api_url
        self.api_key = api_key
        self.model_name = model_name
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        # Ragas gọi hàm này để vector hóa danh sách context
        payload = {"input": texts, "model": self.model_name}
        try:
            # Dùng httpx.post thường (không async)
            response = httpx.post(
                self.api_url, headers=self.headers, json=payload, timeout=60.0
            )
            response.raise_for_status()
            data = response.json()
            # Giả định format trả về chuẩn OpenAI: {"data": [{"embedding": [...]}, ...]}
            return [item["embedding"] for item in data.get("data", [])]
        except Exception as e:
            print(f"❌ Embeddings Error: {e}")
            # Trả về vector rỗng để không crash luồng (hoặc raise tùy bạn)
            return [[] for _ in texts]

    def embed_query(self, text: str) -> List[float]:
        # Ragas gọi hàm này để vector hóa câu hỏi
        result = self.embed_documents([text])
        return result[0] if result else []

    async def embed_text(self, text: str) -> List[float]:
        return self.embed_query(text)
