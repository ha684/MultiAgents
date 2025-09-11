# src/middleware/exception_handler.py
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import json
from datetime import datetime, timezone
from src.utils.logger_conf import logger

async def exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Enhanced global exception handler with envelope format"""
    
    if (
        request.url.path.startswith("/websocket/") or
        request.url.path.startswith("/ws/") or
        request.headers.get("upgrade", "").lower() == "websocket"
    ):
        raise exc
    
    if isinstance(exc, HTTPException):
        status_code = exc.status_code
        error_detail = exc.detail
        error_type = "HTTPException"
    elif isinstance(exc, StarletteHTTPException):
        status_code = exc.status_code
        error_detail = exc.detail
        error_type = "StarletteHTTPException"
    elif isinstance(exc, RequestValidationError):
        status_code = 422
        error_detail = {
            "message": "Validation error",
            "errors": exc.errors()
        }
        error_type = "ValidationError"
    else:
        status_code = 500
        error_detail = "Internal server error"
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
        "error": {
            "type": error_type,
            "detail": error_detail
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "path": request.url.path
    }
    
    if hasattr(request.state, 'request_id'):
        error_envelope["request_id"] = request.state.request_id
    
    return JSONResponse(
        status_code=status_code,
        content=error_envelope
    )

def _is_streaming_request(request: Request) -> bool:
    """Check if request expects streaming response"""
    try:
        if request.url.path.endswith("/ask") or "stream" in request.url.path:
            return True
            
        if request.query_params.get("stream") == "true":
            return True
            
        return False
    except Exception:
        return False

def _create_streaming_error_response(status_code: int, error_type: str, error_detail: str) -> StreamingResponse:
    """Create SSE error response"""
    
    def generate_error_stream():
        error_event = {
            "type": "error",
            "data": {
                "type": error_type,
                "message": error_detail,
                "code": status_code
            },
            "id": None,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        sse_data = json.dumps(error_event, ensure_ascii=False)
        yield f"event: error\ndata: {sse_data}\n\n"
    
    return StreamingResponse(
        generate_error_stream(),
        status_code=status_code,
        media_type="text/event-stream",
        headers={"Content-Type": "text/event-stream"}
    )

def _get_error_message(status_code: int) -> str:
    """Create error message based on status code"""
    messages = {
        400: "Bad request",
        401: "Unauthorized access",
        403: "Access forbidden",
        404: "Resource not found",
        422: "Invalid request data",
        500: "Internal server error"
    }
    return messages.get(status_code, "Request failed")
