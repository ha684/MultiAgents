# src/core/exceptions/chat_exceptions.py

from fastapi import status

from src.core.exceptions.base import BaseException


class ValidationError(BaseException):
    """Raised when validation fails"""

    def __init__(self, message: str, error_code: str | None = None):
        super().__init__(
            message=message,
            error_code=error_code or "VALIDATION_ERROR",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class ConversationNotFoundError(BaseException):
    """Raised when conversation is not found"""

    def __init__(self, conversation_id: str | None = None):
        message = "Conversation not found"
        if conversation_id:
            message = f"Conversation '{conversation_id}' not found"

        super().__init__(
            message=message,
            error_code="CONVERSATION_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class ResearchNotFoundError(BaseException):
    """Raised when research is not found"""

    def __init__(self, conversation_id: str | None = None):
        message = "Running conversation not found"

        super().__init__(
            message=message,
            error_code="RESEARCH_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
        )
