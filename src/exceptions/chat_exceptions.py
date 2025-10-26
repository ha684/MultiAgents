from src.exceptions.base import BaseException
from typing import Optional
from fastapi import status


class ValidationError(BaseException):
    """Raised when validation fails"""

    def __init__(self, message: str, error_code: Optional[str] = None):
        super().__init__(
            message=message,
            error_code=error_code or "VALIDATION_ERROR",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class ConversationNotFoundError(BaseException):
    """Raised when conversation is not found"""

    def __init__(self, conversation_id: Optional[str] = None):
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

    def __init__(self, conversation_id: Optional[str] = None):
        message = "Running conversation not found"

        super().__init__(
            message=message,
            error_code="RESEARCH_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
        )
