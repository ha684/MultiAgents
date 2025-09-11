from typing import Any, Dict
from fastapi import Request
from fastapi.responses import JSONResponse
import json
from datetime import datetime, timezone

class ResponseHandlerMiddleware:
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, request: Request, call_next):
        if (
            request.url.path.startswith("/websocket/") or
            request.url.path.startswith("/ws/") or
            request.url.path == "/health" or
            request.headers.get("upgrade", "").lower() == "websocket"
        ):
            return await call_next(request)
        
        response = await call_next(request)
        if not isinstance(response, JSONResponse):
            return response
            
        if hasattr(response, 'body') and response.body:
            try:
                original_data = json.loads(response.body.decode())
                
                if isinstance(original_data, dict) and 'success' in original_data:
                    return response

                wrapped_data = self._create_envelope(
                    data=original_data,
                    status_code=response.status_code,
                    request=request
                )
                return JSONResponse(
                    content=wrapped_data,
                    status_code=response.status_code,
                    headers=dict(response.headers)
                )
            except (json.JSONDecodeError, AttributeError):
                pass
        
        return response
    
    def _create_envelope(self, data: Any, status_code: int, request: Request) -> Dict[str, Any]:
        """Create standard response handler"""
        is_success = 200 <= status_code < 400
        
        envelope = {
            "success": is_success,
            "status_code": status_code,
            "message": self._get_default_message(status_code, is_success),
            "data": data if is_success else None,
            "error": data if not is_success else None,
            "timestamp": self._get_timestamp(),
            "path": request.url.path
        }
        
        if hasattr(request.state, 'request_id'):
            envelope["request_id"] = request.state.request_id
            
        return envelope
    
    def _get_default_message(self, status_code: int, is_success: bool) -> str:
        """Create default message based on status code handler"""
        if is_success:
            return "Request successful"
        
        error_messages = {
            400: "Bad request",
            401: "Unauthorized",
            403: "Forbidden", 
            404: "Not found",
            422: "Validation error",
            500: "Internal server error"
        }
        return error_messages.get(status_code, "Request failed")
    
    def _get_timestamp(self) -> str:
        """Create timestamp in ISO format handler"""
        return datetime.now(timezone.utc).isoformat()