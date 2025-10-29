# src/middlewares/response_handler.py
from datetime import datetime
import json
from typing import Any, Dict
from zoneinfo import ZoneInfo

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from src.utils.logger_conf import logger


class ResponseHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if (
            request.url.path.startswith("/websocket/")
            or request.url.path.startswith("/ws/")
            or request.url.path == "/health"
            or request.url.path == "/openapi.json"
            or request.url.path == "/docs"
            or request.url.path == "/redoc"
            or request.url.path.startswith("/docs/")
            or request.url.path.startswith("/redoc/")
            or request.headers.get("upgrade", "").lower() == "websocket"
        ):
            return await call_next(request)

        response = await call_next(request)
        content_type = response.headers.get("content-type")
        if not content_type or "application/json" not in content_type:
            logger.info(
                f"Skipping non-JSON response for path: {request.url.path} (Content-Type: {content_type})"
            )
            return response

        response_body = b""
        async for chunk in response.body_iterator:
            response_body += chunk

        if not response_body:
            headers = {
                k: v
                for k, v in response.headers.items()
                if k.lower() != "content-length"
            }
            return Response(status_code=response.status_code, headers=headers)

        try:
            original_data = json.loads(response_body.decode())

            # Check if response is already wrapped (has "success" field)
            if isinstance(original_data, dict) and "success" in original_data:
                headers = {
                    k: v
                    for k, v in response.headers.items()
                    if k.lower() != "content-length"
                }
                return JSONResponse(
                    content=original_data,
                    status_code=response.status_code,
                    headers=headers,
                )

            # Handle HTTPException responses properly
            if isinstance(original_data, dict) and "detail" in original_data:
                wrapped_data = self._create_envelope(
                    data=original_data,
                    status_code=response.status_code,
                    request=request,
                )
            else:
                wrapped_data = self._create_envelope(
                    data=original_data,
                    status_code=response.status_code,
                    request=request,
                )

            headers = {
                k: v
                for k, v in response.headers.items()
                if k.lower() != "content-length"
            }
            return JSONResponse(
                content=wrapped_data, status_code=response.status_code, headers=headers
            )
        except (json.JSONDecodeError, AttributeError) as e:
            logger.warning(f"Could not wrap response body for {request.url.path}: {e}")
            headers = {
                k: v
                for k, v in response.headers.items()
                if k.lower() != "content-length"
            }
            return Response(
                content=response_body,
                status_code=response.status_code,
                headers=headers,
                media_type=response.media_type,
            )

    def _create_envelope(
        self, data: Any, status_code: int, request: Request
    ) -> Dict[str, Any]:
        """Create standard response envelope"""
        is_success = 200 <= status_code < 400

        # Handle HTTPException detail properly
        if isinstance(data, dict) and "detail" in data and not is_success:
            error_detail = data["detail"]
        else:
            error_detail = data if not is_success else None

        envelope = {
            "success": is_success,
            "status_code": status_code,
            "message": self._get_default_message(status_code, is_success),
            "data": data if is_success else None,
            "error": error_detail,
            "timestamp": self._get_timestamp(),
            "path": request.url.path,
        }

        if hasattr(request.state, "request_id"):
            envelope["request_id"] = request.state.request_id

        return envelope

    def _get_default_message(self, status_code: int, is_success: bool) -> str:
        """Create default message based on status code"""
        if is_success:
            return "Request successful"

        error_messages = {
            400: "Bad request",
            401: "Unauthorized",
            403: "Forbidden",
            404: "Not found",
            422: "Validation error",
            500: "Internal server error",
        }
        return error_messages.get(status_code, "Request failed")

    def _get_timestamp(self) -> str:
        """Create timestamp in ISO format"""
        return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat()
