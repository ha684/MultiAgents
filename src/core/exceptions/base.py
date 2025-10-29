# src/core/exceptions/base.py
from typing import Optional


class BaseException(Exception):
    """Base exception for all service errors"""

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        status_code: int = 500,
    ):
        self.message = message
        self.error_code = error_code or self.__class__.__name__.upper()
        self.status_code = status_code
        super().__init__(self.message)

    def __str__(self) -> str:
        return f"{self.__class__.__name__}: {self.message}"

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"message='{self.message}', "
            f"error_code='{self.error_code}', "
            f"status_code={self.status_code})"
        )
