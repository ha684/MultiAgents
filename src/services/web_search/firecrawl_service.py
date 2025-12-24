# src/services/web_search/firecrawl_service.py

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
        """Searches using Firecrawl API and scrapes full content."""
        if not self.api_base_url:
            raise ValueError("FIRECRAWL_API_URL not found in environment variables")

        try:
            logger.info(
                f"Searching Firecrawl for: '{query}' with max_results={max_results}"
            )
            search_endpoint = f"{self.api_base_url}/v1/search"

            # --- CẤU HÌNH QUAN TRỌNG ---
            # Mặc định yêu cầu Firecrawl vào trang lấy nội dung Markdown
            default_scrape_options = {
                "formats": ["markdown"],
            }

            # Merge scrapeOptions từ kwargs nếu người dùng có truyền thêm (ví dụ: excludeTags)
            user_scrape_options = kwargs.get("scrapeOptions", {})
            final_scrape_options = {**default_scrape_options, **user_scrape_options}

            payload = {
                "query": query,
                "limit": max_results,
                "scrapeOptions": final_scrape_options,  # Thêm dòng này
            }

            # Các tham số khác (location, lang...)
            valid_params = {
                "location",
                "country",
                "language",
                "tbs",
                "filter",
                # "scrapeOptions", # Đã xử lý ở trên
            }
            payload.update({k: v for k, v in kwargs.items() if k in valid_params})

            headers = {"Content-Type": "application/json", "Accept": "application/json"}

            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            # Tăng timeout vì crawl nội dung tốn thời gian hơn search metadata
            timeout = kwargs.get("timeout", 60)

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    search_endpoint,
                    json=payload,
                    headers=headers,
                    timeout=timeout,
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
                # --- LẤY NỘI DUNG MARKDOWN ---
                # Ưu tiên lấy markdown, nếu không có mới lấy description
                content = item.get("markdown")
                if not content:
                    content = item.get("description", "No Content")

                standardized_results.append(
                    {
                        "title": item.get("title", "No Title"),
                        "content": content,  # Content giờ là full markdown
                        "url": item.get("url"),
                        # Có thể lưu thêm metadata nếu cần
                        "metadata": item.get("metadata", {}),
                    }
                )

            if not standardized_results:
                logger.warning("No valid results after standardization.")
                return None

            return self._format_to_documents(standardized_results)
        except Exception as e:
            logger.error(f"An unexpected error occurred during Firecrawl search: {e}")
            return None
