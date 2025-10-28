from typing import List
from langchain_core.embeddings import Embeddings
from pydantic import BaseModel, ConfigDict
import httpx
import asyncio
import logging

logger = logging.getLogger(__name__)


class InferenceAPIEmbeddings(BaseModel, Embeddings):
    """Embed texts using the API.

    Requires a Inference API key and a model name.
    """

    model_config = ConfigDict(extra="allow", protected_namespaces=())

    api_key: str
    model_name: str
    api_url: str
    retries: int = 3
    batch_size: int = 16

    def __init__(
        self,
        api_key: str,
        model_name: str,
        api_url: str,
        retries: int = 3,
        batch_size: int = 16,
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

    async def embed(self, texts: List[str]) -> List[List[float]]:
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

    async def embed_query(self, text: str) -> List[float]:
        """Embed a single query text."""
        embeddings = await self.embed([text])
        return embeddings[0]

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
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

    def embed_query_sync(self, text: str) -> List[float]:
        """Synchronous wrapper for embed_query."""
        return asyncio.run(self.embed_query(text))

    def embed_documents_sync(self, texts: List[str]) -> List[List[float]]:
        """Synchronous wrapper for embed_documents."""
        return asyncio.run(self.embed_documents(texts))
