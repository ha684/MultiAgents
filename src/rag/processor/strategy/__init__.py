"""
Strategy module for document processing.
This module contains different document processing strategies.
"""

from typing import Dict, Any
from src.rag.processor.strategy.naive import NaiveStrategy
from src.db.models.document import Document as DBDocument
from src.rag.processor.strategy.base import BaseStrategy
from pathlib import Path
from src.rag.processor.strategy.image import ImageStrategy
from src.rag.processor.strategy.spreadsheet import SpreadsheetStrategy


def get_strategy(document: DBDocument, config: Dict[str, Any]) -> BaseStrategy:
    """
    Factory method to get the appropriate strategy based on the document.
    Args:
        document: The database document object
        config: Configuration parameters for the strategy
    Returns:
        An instance of the appropriate strategy
    """
    file_extension = Path(document.file_path).suffix.lower()
    if file_extension in [".jpg", ".jpeg", ".png"]:
        return ImageStrategy(config)
    if file_extension in [".xlsx", ".xls"]:
        return SpreadsheetStrategy(config=config)
    return NaiveStrategy(config)
