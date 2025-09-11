"""
Strategy module for document processing.
This module contains different document processing strategies.
"""

from typing import Dict, Any
from src.rag.processor.strategy.base import BaseStrategy
from src.rag.processor.strategy.image import ImageStrategy
from src.rag.processor.strategy.naive import NaiveStrategy
from src.rag.processor.strategy.spreadsheet import SpreadsheetStrategy
from src.db.models.document import Document


def get_strategy(document: Document, config: Dict[str, Any]) -> BaseStrategy:
    """
    Factory method to get the appropriate strategy based on the document.

    Args:
        document: The document to process
        config: Configuration parameters for the strategy

    Returns:
        An instance of BaseStrategy or its subclass
    """
    if document.file_type in ["jpg", "jpeg", "png"]:
        return ImageStrategy(config)
    elif document.file_type in ["xlsx"]:
        return SpreadsheetStrategy(config)
    else:
        return NaiveStrategy(config)


__all__ = [
    "BaseStrategy",
    "NaiveStrategy",
    "ImageStrategy",
    "SpreadsheetStrategy",
    "get_strategy",
]
