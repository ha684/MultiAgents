# src/middleware/response_handler.py
from typing import Any, Optional, Dict, List, Union
from datetime import datetime
from fastapi import Request, HTTPException, status
from pydantic import BaseModel
import math
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from src.models.auth import StandardResponse


class PaginationMeta(BaseModel):
    """Pagination metadata"""

    page: int
    size: int
    total: int
    pages: int
    has_next: bool
    has_prev: bool


class PaginatedResponse(StandardResponse):
    """Response model for paginated data"""

    pagination: PaginationMeta


def create_success_response(
    request: Request,
    data: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
    message: str = "Success",
    status_code: int = status.HTTP_200_OK,
) -> StandardResponse:
    """
    Create a standardized success response

    Args:
        request: FastAPI request object
        data: Response data (optional)
        message: Success message
        status_code: HTTP status code (default: 200)

    Returns:
        StandardResponse object
    """
    return StandardResponse(
        success=True,
        message=message,
        data=data,
        timestamp=datetime.now(),
        request_id=getattr(request.state, "request_id", None),
        status_code=status_code,
    )


def create_error_response(
    request: Request,
    message: str = "An error occurred",
    error_code: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
    status_code: int = status.HTTP_400_BAD_REQUEST,
) -> StandardResponse:
    """
    Create a standardized error response

    Args:
        request: FastAPI request object
        message: Error message
        error_code: Specific error code for client handling
        data: Additional error data (optional)
        status_code: HTTP status code (default: 400)

    Returns:
        StandardResponse object
    """
    error_data = data or {}
    if error_code:
        error_data["error_code"] = error_code

    return StandardResponse(
        success=False,
        message=message,
        data=error_data if error_data else None,
        timestamp=datetime.now(),
        request_id=getattr(request.state, "request_id", None),
        status_code=status_code,
    )


def create_paginated_response(
    request: Request,
    data: List[Dict[str, Any]],
    page: int,
    size: int,
    total: int,
    message: str = "Data retrieved successfully",
) -> PaginatedResponse:
    """
    Create a standardized paginated response

    Args:
        request: FastAPI request object
        data: List of data items
        page: Current page number
        size: Page size
        total: Total number of items
        message: Success message

    Returns:
        PaginatedResponse object
    """
    pages = math.ceil(total / size) if total > 0 else 0
    has_next = page < pages
    has_prev = page > 1

    pagination_meta = PaginationMeta(
        page=page,
        size=size,
        total=total,
        pages=pages,
        has_next=has_next,
        has_prev=has_prev,
    )

    return PaginatedResponse(
        success=True,
        message=message,
        data=data,
        pagination=pagination_meta,
        timestamp=datetime.now(),
        request_id=getattr(request.state, "request_id", None),
        status_code=status.HTTP_200_OK,
    )


def handle_http_exception(request: Request, exc: HTTPException) -> StandardResponse:
    """
    Convert HTTPException to standardized error response

    Args:
        request: FastAPI request object
        exc: HTTPException instance

    Returns:
        StandardResponse object
    """
    return create_error_response(
        request=request, message=str(exc.detail), status_code=exc.status_code
    )


def handle_validation_error(
    request: Request, errors: List[Dict[str, Any]]
) -> StandardResponse:
    """
    Handle Pydantic validation errors

    Args:
        request: FastAPI request object
        errors: List of validation errors

    Returns:
        StandardResponse object
    """
    formatted_errors = []
    for error in errors:
        formatted_errors.append(
            {
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
        )

    return create_error_response(
        request=request,
        message="Validation failed",
        error_code="VALIDATION_ERROR",
        data={"errors": formatted_errors},
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


# Helper function for adding request tracking middleware
def add_request_id_middleware():
    """
    Middleware to add unique request IDs for tracking
    This should be added to your FastAPI app
    """

    class RequestIDMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            request.state.request_id = str(uuid.uuid4())
            response = await call_next(request)
            response.headers["X-Request-ID"] = request.state.request_id
            return response

    return RequestIDMiddleware
