"""
Strategy module for document processing.
This module contains different document processing strategies.
"""

from typing import Dict, Any
from src.rag.processor.strategy.naive import NaiveStrategy


def get_strategy(config: Dict[str, Any]) -> NaiveStrategy:
    """
    Factory method to get the appropriate strategy based on the document.
    Args:
        document: The document to process
        config: Configuration parameters for the strategy
    Returns:
        An instance of NaiveStrategy
    """
    return NaiveStrategy(config)
