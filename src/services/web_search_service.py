from typing import List, Optional, Any, Dict
from langchain_core.documents import Document
from src.services.web_search.base import BaseSearchService
from src.services.web_search.tavily import TavilyService
from src.services.web_search.firecrawl import FireCrawlService
from src.models.chat import SearchProvider
from src.utils.logger_conf import logger


class SearchService:
    """
    Search service that routes requests to appropriate search providers.
    """

    def __init__(self):
        """Initialize the unified search service with all available providers."""
        self._providers: Dict[SearchProvider, BaseSearchService] = {
            SearchProvider.TAVILY: TavilyService(),
            SearchProvider.FIRECRAWL: FireCrawlService(),
        }
        logger.info(
            f"UnifiedSearchService initialized with providers: {list(self._providers.keys())}",
        )

    async def search(
        self,
        query: str,
        provider: SearchProvider,
        api_key: str,
        max_results: int = 5,
        **kwargs: Any,
    ) -> Optional[List[Document]]:
        """
        Search using the specified provider.
        """
        target_provider = provider
        try:
            service = self._providers[provider]
            result = await service.search(api_key, query, max_results, **kwargs)
            if result:
                logger.info(f"Search successful with provider: {target_provider.value}")
                return result
            else:
                logger.warning(f"No results from provider: {target_provider.value}")
                return []
        except Exception as e:
            logger.error(f"Error with provider {target_provider.value}: {e}")
            raise e

    def get_available_providers(self) -> List[SearchProvider]:
        """Get list of available search providers."""
        return list(self._providers.keys())


search_service = SearchService()
