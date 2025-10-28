from abc import ABC, abstractmethod
from langchain_core.documents import Document
from typing import Dict, Any, List
from src.db.models.document import Document as DBDocument


class BaseStrategy(ABC):
    """
    Base class for document chunking strategies.
    All concrete strategies should inherit from this class and implement the chunk method.
    """

    _supported_file_types: List[str] = []

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the strategy with configuration.

        Args:
            config: Dictionary containing configuration parameters
        """
        self.config = config

    @classmethod
    def get_supported_file_types(cls) -> List[str]:
        """
        Get the list of supported file types for this strategy.

        Returns:
            A list of file type strings (e.g., ['pdf', 'txt', 'docx'])
        """
        return cls._supported_file_types

    def check_file_type(self, file_path: str) -> bool:
        """
        Check if the file type is supported by this strategy.

        Args:
            file_path: Path to the document file

        Returns:
            True if the file type is supported, False otherwise
        """
        file_extension = file_path.split(".")[-1].lower()
        if not self._supported_file_types:
            return True
        return file_extension in self._supported_file_types

    @abstractmethod
    def chunk(self, file_path: str, document: DBDocument) -> List[Document]:
        """
        Process a document file according to the strategy.

        Args:
            file_path: Path to the document file
            document: Document data (optional)

        Returns:
            A list of Langchain Document objects
        """
        raise NotImplementedError("Subclasses should implement this method.")
