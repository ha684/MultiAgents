from typing import List, Optional, Any, Dict, Union
from langchain_core.documents import Document
from src.services.web_search.base import BaseSearchService
from src.services.web_search.tavily import TavilyService
from src.services.web_search.firecrawl import FireCrawlService
from src.models.chat import SearchProvider
from src.config.settings import settings
from src.utils.logger_conf import logger

Provider = Union[str, SearchProvider]


def get_api_key_for_provider(provider: SearchProvider) -> str:
    """Get API key based on the selected provider."""
    if provider == SearchProvider.TAVILY:
        return settings.tavily_api_key
    elif provider == SearchProvider.FIRECRAWL:
        return settings.firecrawl_api_key


def normalize_provider(p: Provider) -> SearchProvider:
    if isinstance(p, SearchProvider):
        return p
    s = p.strip()
    try:
        return SearchProvider(s.lower())
    except ValueError:
        try:
            return SearchProvider[s.upper()]
        except KeyError:
            valid = [e.value for e in SearchProvider]
            raise ValueError(f"Unknown provider {p!r}. Valid: {valid}")


class WebSearchService:
    """
    Search service that routes requests to appropriate search providers.
    """

    def __init__(self):
        """Initialize the unified search service with all available providers."""
        self._providers: Dict[SearchProvider, BaseSearchService] = {
            SearchProvider.TAVILY: TavilyService(),
            SearchProvider.FIRECRAWL: FireCrawlService(),
        }

    async def search(
        self,
        query: str,
        provider: Provider,
        api_key: Optional[str] = None,
        max_results: int = 5,
        **kwargs: Any,
    ) -> Optional[List[Document]]:
        """
        Search using the specified provider.
        """
        target_provider = normalize_provider(provider)
        api_key = api_key or get_api_key_for_provider(target_provider)
        try:
            service = self._providers[target_provider]
            result = await service.search(api_key, query, max_results, **kwargs)
            if result:
                logger.info(f"Search successful with provider: {target_provider.value}")
                return result
            else:
                logger.warning(f"No results from provider: {target_provider.value}")
                return []
        except Exception as e:
            logger.error(f"Error with provider {target_provider.value}")
            raise e

    def get_available_providers(self) -> List[SearchProvider]:
        """Get list of available search providers."""
        return list(self._providers.keys())


web_search_service = WebSearchService()
