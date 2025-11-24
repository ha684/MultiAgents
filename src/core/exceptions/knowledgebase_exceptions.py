from fastapi import status

from src.core.exceptions.base import BaseException


class KnowledgeBaseNotFoundError(BaseException):
    """Raised when knowledge base is not found"""

    def __init__(self, message: str):
        super().__init__(
            message=message,
            error_code="KNOWLEDGE_BASE_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
        )
