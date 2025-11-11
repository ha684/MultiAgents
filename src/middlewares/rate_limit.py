# src/middlewares/rate_limit.py
from typing import Callable, Optional

from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src.core.config.settings import RATE_LIMIT_CONFIG
from src.core.security import JWTManager
from src.infrastructure.cache import redis_client
from src.utils.logger_conf import logger


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware"""

    def __init__(self, app):
        super().__init__(app)
        self.redis_client = redis_client
        self.config = RATE_LIMIT_CONFIG

        self.route_configs = {
            "/auth/login": self.config["auth"],
            "/auth/register": self.config["auth"],
            "/auth/password/reset": self.config["password_reset"],
            "/auth/password/reset/confirm": self.config["password_reset"],
        }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process rate limiting for requests"""

        if self._should_skip_rate_limiting(request):
            return await call_next(request)

        rate_config = self._get_rate_config(request)
        if not rate_config:
            return await call_next(request)

        rate_limit_key = self._create_rate_limit_key(request)

        allowed, limit_info = await self.redis_client.rate_limit(
            rate_limit_key,
            rate_config["requests"],
            int(rate_config["window"].total_seconds()),
        )

        if not allowed:
            logger.warning(
                f"Rate limit exceeded for {rate_limit_key}: "
                f"{request.method} {request.url.path}"
            )

            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "success": False,
                    "message": "Rate limit exceeded",
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "metadata": {
                        "limit": limit_info["limit"],
                        "remaining": limit_info["remaining"],
                        "reset_time": limit_info["reset_time"].isoformat(),
                        "retry_after": limit_info["retry_after"],
                    },
                },
                headers={
                    "X-RateLimit-Limit": str(limit_info["limit"]),
                    "X-RateLimit-Remaining": str(limit_info["remaining"]),
                    "X-RateLimit-Reset": str(int(limit_info["reset_time"].timestamp())),
                    "Retry-After": str(limit_info["retry_after"]),
                },
            )

        response = await call_next(request)

        if hasattr(response, "headers"):
            response.headers["X-RateLimit-Limit"] = str(limit_info["limit"])
            response.headers["X-RateLimit-Remaining"] = str(limit_info["remaining"])
            response.headers["X-RateLimit-Reset"] = str(
                int(limit_info["reset_time"].timestamp())
            )

        return response

    def _should_skip_rate_limiting(self, request: Request) -> bool:
        """Check if rate limiting should be skipped for this request"""
        if request.url.path == "/health" or request.url.path == "/metrics":
            return True

        if (
            request.url.path.startswith("/ws/")
            or request.url.path.startswith("/websocket/")
            or request.headers.get("upgrade", "").lower() == "websocket"
        ):
            return True

        if request.method == "OPTIONS":
            return True

        return False

    def _get_rate_config(self, request: Request) -> Optional[dict]:
        """Get rate limit configuration for the current route"""
        path = request.url.path

        if path in self.route_configs:
            return self.route_configs[path]

        for route_path, config in self.route_configs.items():
            if path.startswith(route_path.rstrip("*")):
                return config

        return self.config["default"]

    def _create_rate_limit_key(self, request: Request) -> str:
        """Create rate limit key for the request"""
        client_ip = self._get_client_ip(request)

        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            try:
                token = auth_header.split(" ")[1]
                token_data = JWTManager.verify_token(token)
                if token_data:
                    return f"user:{token_data.user_id}:{request.url.path}"
            except Exception:
                pass

        return f"ip:{client_ip}:{request.url.path}"

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address from request"""
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        return request.client.host if request.client else "unknown"
