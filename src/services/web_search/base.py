# src/services/web_search/base.py
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from langchain_core.documents import Document


class BaseSearchService(ABC):
    """
    Abstract Base Class for web search services.
    """

    @abstractmethod
    async def search(
        self, api_key: str, query: str, max_results: int = 5, **kwargs: Any
    ) -> Optional[List[Document]]:
        """
        Performs a search and returns a list of Document objects.

        Args:
            api_key (str): The API key for the search provider.
            query (str): The search query.
            max_results (int): The maximum number of results to return.
            **kwargs: Provider-specific arguments.

        Returns:
            Optional[List[Document]]: A list of Document objects or None if no results.
        """
        pass

    def _format_to_documents(self, results: List[Dict[str, Any]]) -> List[Document]:
        """
        Helper method to format a standardized list of dicts into Document objects.
        """
        documents = []
        for result in results:
            context = f"--- # Title: {result.get('title', 'No Title')} ---\n"
            context += f"Content : {result.get('content', 'No Content')}\n"

            document = Document(
                page_content=context,
                metadata={
                    "original_filename": result.get("url", ""),
                    "favicon": result.get("favicon", ""),
                },
            )
            documents.append(document)
        return documents
