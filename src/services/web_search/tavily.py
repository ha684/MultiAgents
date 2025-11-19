# src/services/web_search/tavily.py
from typing import Any

from langchain_core.documents import Document
from tavily import AsyncTavilyClient

from src.services.web_search.base import BaseSearchService
from src.utils.logger_conf import logger


class TavilyService(BaseSearchService):
    """Service for collecting content using Tavily API"""

    async def search(
        self, api_key: str, query: str, max_results: int = 5, **kwargs: Any
    ) -> list[Document] | None:
        """Searches using Tavily API with a provided key."""
        if not api_key:
            raise ValueError("Tavily API key must be provided for searching.")

        try:
            client = AsyncTavilyClient(api_key=api_key)
            search_depth = kwargs.get("search_depth", "basic")
            topic = kwargs.get("topic", "general")
            time_range = kwargs.get("time_range", "day")
            start_date = kwargs.get("start_date")
            end_date = kwargs.get("end_date")
            days = kwargs.get("days", 365)
            include_answer = kwargs.get("include_answer")
            include_raw_content = kwargs.get("include_raw_content", "text")
            country = kwargs.get("country")

            results = await client.search(
                query=query,
                search_depth=search_depth,
                max_results=max_results,
                topic=topic,
                time_range=time_range,
                start_date=start_date,
                end_date=end_date,
                days=days,
                include_answer=include_answer,
                include_raw_content=include_raw_content,
                country=country,
                include_favicon=True,
            )
            unique_results = {}
            for result in results.get("results", []):
                url = result.get("url")
                if url and url not in unique_results:
                    unique_results[url] = {
                        "title": result.get("title"),
                        "content": (
                            result.get("raw_content")
                            if result.get("raw_content")
                            else result.get("content")
                        ),
                        "url": url,
                        "favicon": result.get("favicon"),
                    }
            if not unique_results:
                logger.warning("Tavily search returned no unique results.")
                return None

            standardized_list = list(unique_results.values())
            return self._format_to_documents(standardized_list)

        except Exception as e:
            logger.error(f"An error occurred during Tavily search: {e}")
            raise ValueError(str(e))
