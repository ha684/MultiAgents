# src/core/exceptions/chunk_exceptions.py
from fastapi import status

from src.core.exceptions.base import BaseException


class ChunkNotFoundError(BaseException):
    """Raised when chunk is not found"""

    def __init__(self, message: str):
        super().__init__(
            message=message,
            error_code="CHUNK_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
        )
