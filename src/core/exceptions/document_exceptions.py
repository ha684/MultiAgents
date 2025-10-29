# src/core/exceptions/document_exceptions.py

from fastapi import status

from src.core.exceptions.base import BaseException


class DocumentProcessingError(BaseException):
    """Raised when document processing fails"""

    def __init__(self, message: str):
        super().__init__(
            message=message,
            error_code="DOCUMENT_PROCESSING_ERROR",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class DocumentNotFoundError(BaseException):
    """Raised when document is not found"""

    def __init__(self, message: str):
        super().__init__(
            message=message,
            error_code="DOCUMENT_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class DuplicateDocumentError(BaseException):
    """Raised when a duplicate document is found"""

    def __init__(self, message: str):
        super().__init__(
            message=message,
            error_code="DUPLICATE_DOCUMENT",
            status_code=status.HTTP_409_CONFLICT,
        )
