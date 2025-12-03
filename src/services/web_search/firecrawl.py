# src/services/web_search/firecrawl.py

from typing import Any

import httpx
from langchain_core.documents import Document

from src.core.config.settings import settings
from src.services.web_search.base import BaseSearchService
from src.utils.logger_conf import logger


class FireCrawlService(BaseSearchService):
    """Stateless implementation for a self-hosted Firecrawl service."""

    def __init__(self, api_url: str = None):
        self.api_base_url = settings.firecrawl_api_url or api_url
        self.api_base_url = self.api_base_url.rstrip("/") if self.api_base_url else None

    async def search(
        self, api_key: str | None, query: str, max_results: int = 5, **kwargs: Any
    ) -> list[Document] | None:
        """Searches using Firecrawl API with an optional provided key."""
        if not self.api_base_url:
            raise ValueError("FIRECRAWL_API_URL not found in environment variables")

        try:
            logger.info(
                f"Searching Firecrawl for: '{query}' with max_results={max_results}"
            )
            search_endpoint = f"{self.api_base_url}/v1/search"
            payload = {
                "query": query,
                "limit": max_results,
            }
            valid_params = {
                "location",
                "country",
                "language",
                "tbs",
                "filter",
                "scrapeOptions",
                "formats",
                "includeTags",
                "excludeTags",
            }
            payload.update({k: v for k, v in kwargs.items() if k in valid_params})

            headers = {"Content-Type": "application/json", "Accept": "application/json"}

            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    search_endpoint,
                    json=payload,
                    headers=headers,
                    timeout=kwargs.get("timeout", 30),
                )
                response.raise_for_status()
                raw_results = response.json()

            if not raw_results.get("success", False):
                logger.warning(f"Firecrawl API returned success=False: {raw_results}")
                return None

            results_data = raw_results.get("data", [])

            if not results_data:
                logger.warning("Firecrawl search returned no results in data array.")
                return None

            standardized_results = []
            for item in results_data:
                standardized_results.append(
                    {
                        "title": item.get("title", "No Title"),
                        "content": item.get("description", "No Content"),
                        "url": item.get("url"),
                    }
                )

            if not standardized_results:
                logger.warning("No valid results after standardization.")
                return None

            return self._format_to_documents(standardized_results)
        except Exception as e:
            logger.error(f"An unexpected error occurred during Firecrawl search: {e}")
            return None
