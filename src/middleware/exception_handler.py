# src/middleware/exception_handler.py
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from src.exceptions.base import BaseException
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from src.utils.logger_conf import logger
from typing import Dict, Any


async def exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Enhanced global exception handler for BaseException architecture"""

    if (
        request.url.path.startswith("/websocket/")
        or request.url.path.startswith("/ws/")
        or request.headers.get("upgrade", "").lower() == "websocket"
    ):
        raise exc

    if isinstance(exc, BaseException):
        status_code = exc.status_code
        error_detail = {
            "message": exc.message,
            "code": exc.error_code,
        }
        error_type = exc.__class__.__name__

        if status_code >= 500:
            logger.error(f"Server error: {exc.message}")
        elif status_code >= 400:
            logger.warning(f"Client error: {exc.message}")
        else:
            logger.info(f"Service exception: {exc.message}")

    elif isinstance(exc, HTTPException):
        status_code = exc.status_code
        error_detail = {
            "message": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
            "code": "HTTP_EXCEPTION",
        }
        error_type = "HTTPException"

        logger.warning(
            f"HTTP exception: {exc.detail}",
            extra={"path": request.url.path, "status_code": status_code},
        )

    elif isinstance(exc, ValueError):
        status_code = 400
        error_detail = {
            "message": str(exc),
            "code": "INVALID_VALUE",
        }
        error_type = "ValueError"

        logger.warning(
            f"ValueError: {exc}",
            extra={"path": request.url.path, "exception_str": str(exc)},
        )

    elif isinstance(exc, TypeError):
        status_code = 400
        error_detail = {
            "message": str(exc),
            "code": "INVALID_TYPE",
        }
        error_type = "TypeError"
        logger.warning(f"TypeError: {exc}")

    elif isinstance(exc, KeyError):
        missing_key = str(exc).strip("'\"")
        status_code = 400
        error_detail = {
            "message": f"Missing required field: {missing_key}",
            "code": "MISSING_FIELD",
        }
        error_type = "KeyError"
        logger.warning(f"KeyError: {exc}")

    elif isinstance(exc, AttributeError):
        status_code = 500
        error_detail = {
            "message": "Internal server error - attribute access failed",
            "code": "ATTRIBUTE_ERROR",
        }
        error_type = "AttributeError"

        logger.error(f"AttributeError: {exc}")

    elif isinstance(exc, PermissionError):
        status_code = 403
        error_detail = {
            "message": "Permission denied",
            "code": "PERMISSION_DENIED",
        }
        error_type = "PermissionError"

        logger.warning(f"PermissionError: {exc}")

    elif isinstance(exc, FileNotFoundError):
        status_code = 404
        error_detail = {
            "message": "Resource not found",
            "code": "RESOURCE_NOT_FOUND",
        }
        error_type = "FileNotFoundError"

        logger.warning(f"FileNotFoundError: {exc}")

    else:
        status_code = 500
        error_detail = {
            "message": "Internal server error",
            "code": "INTERNAL_ERROR",
        }
        error_type = type(exc).__name__

        logger.exception(f"Unhandled exception: {exc}")

    is_streaming_request = _is_streaming_request(request)

    if is_streaming_request:
        return _create_streaming_error_response(status_code, error_type, error_detail)

    error_envelope = {
        "success": False,
        "status_code": status_code,
        "message": _get_error_message(status_code),
        "data": None,
        "error": {"type": error_type, "detail": error_detail},
        "timestamp": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat(),
        "path": request.url.path,
    }

    if hasattr(request.state, "request_id"):
        error_envelope["request_id"] = request.state.request_id

    correlation_id = request.headers.get("x-correlation-id")
    if correlation_id:
        error_envelope["correlation_id"] = correlation_id

    return JSONResponse(status_code=status_code, content=error_envelope)


def _format_validation_errors(errors: list) -> list:
    """Format FastAPI validation errors for better readability"""
    formatted_errors = []
    for error in errors:
        formatted_error = {
            "field": ".".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"],
        }

        if "input" in error:
            input_value = error["input"]
            sensitive_fields = ["password", "token", "secret", "key", "auth"]
            field_name = formatted_error["field"].lower()

            if not any(sensitive in field_name for sensitive in sensitive_fields):
                formatted_error["input"] = input_value
            else:
                formatted_error["input"] = "[REDACTED]"

        if "ctx" in error:
            formatted_error["context"] = error["ctx"]

        formatted_errors.append(formatted_error)

    return formatted_errors


def _is_streaming_request(request: Request) -> bool:
    """Check if request expects streaming response"""
    try:
        streaming_paths = ["/ask/sse", "/stream", "/events"]
        if any(request.url.path.endswith(path) for path in streaming_paths):
            return True

        accept_header = request.headers.get("accept", "").lower()
        if "text/event-stream" in accept_header:
            return True

        if request.query_params.get("stream") == "true":
            return True

        return False
    except Exception:
        return False


def _create_streaming_error_response(
    status_code: int, error_type: str, error_detail: Dict[str, Any]
) -> StreamingResponse:
    """Create SSE error response with proper formatting"""

    def generate_error_stream():
        error_event = {
            "type": "error",
            "data": {
                "type": error_type,
                "message": error_detail.get("message", "Unknown error"),
                "code": error_detail.get("code", "UNKNOWN_ERROR"),
                "status_code": status_code,
            },
            "id": f"error_{int(datetime.now().timestamp())}",
            "timestamp": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat(),
        }

        sse_data = json.dumps(error_event, ensure_ascii=False)
        yield "event: error\n"
        yield f"data: {sse_data}\n"
        yield f"id: {error_event['id']}\n\n"

        yield "event: end\n"
        yield "data: {{}}\n\n"

    return StreamingResponse(
        generate_error_stream(),
        status_code=status_code,
        media_type="text/event-stream",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _get_error_message(status_code: int) -> str:
    """Create human-readable error message based on status code"""
    messages = {
        400: "Bad request - invalid input data",
        401: "Unauthorized - authentication required",
        403: "Forbidden - access denied",
        404: "Not found - resource does not exist",
        405: "Method not allowed",
        409: "Conflict - resource already exists",
        422: "Unprocessable entity - validation failed",
        429: "Too many requests - rate limit exceeded",
        500: "Internal server error",
        501: "Not implemented",
        502: "Bad gateway - upstream service error",
        503: "Service unavailable",
        504: "Gateway timeout - upstream service timeout",
    }
    return messages.get(status_code, f"Request failed with status {status_code}")
