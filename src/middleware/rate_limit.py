# src/middleware/rate_limiting.py
import time
from typing import Dict, Optional, Callable, Any, Tuple
from datetime import datetime
from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import redis
from src.config.auth_settings import RATE_LIMIT_CONFIG
from src.services.security_services import jwt_manager
from src.utils.logger_conf import logger
from dotenv import load_dotenv
import os
from zoneinfo import ZoneInfo

load_dotenv()


class RedisRateLimiter:
    """Redis-based rate limiter"""

    def __init__(
        self, redis_client: Optional[redis.Redis] = None, key_prefix: str = "rate_limit"
    ):
        """
        Initialize Redis rate limiter

        Args:
            redis_client: Redis client instance. If None, creates default connection
            key_prefix: Prefix for Redis keys to avoid collisions
        """
        self.redis = redis_client or redis.Redis(
            host=os.getenv("REDIS_HOST", "redis"),
            port=os.getenv("REDIS_PORT", 6379),
            db=0,
            decode_responses=True,
        )
        self.key_prefix = key_prefix

    def _get_redis_key(self, key: str) -> str:
        """Generate Redis key with prefix"""
        return f"{self.key_prefix}:{key}"

    def is_allowed(
        self, key: str, limit: int, window_seconds: int
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if request is allowed under rate limit using Redis

        This uses a sliding window approach with Redis sorted sets
        """
        now = time.time()
        redis_key = self._get_redis_key(key)

        pipe = self.redis.pipeline()

        try:
            pipe.zremrangebyscore(redis_key, 0, now - window_seconds)

            pipe.zcard(redis_key)

            results = pipe.execute()
            current_count = results[1]

            if current_count >= limit:
                oldest_requests = self.redis.zrange(redis_key, 0, 0, withscores=True)
                if oldest_requests:
                    oldest_time = oldest_requests[0][1]
                    retry_after = int(window_seconds - (now - oldest_time)) + 1
                else:
                    retry_after = window_seconds

                return False, {
                    "limit": limit,
                    "remaining": 0,
                    "reset_time": datetime.fromtimestamp(
                        oldest_time + window_seconds, tz=ZoneInfo("Asia/Ho_Chi_Minh")
                    )
                    if oldest_requests
                    else datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")),
                    "retry_after": retry_after,
                }
            unique_score = now + (time.time_ns() % 1000000) / 1000000000
            self.redis.zadd(redis_key, {str(unique_score): unique_score})
            self.redis.expire(redis_key, window_seconds + 1)
            oldest_requests = self.redis.zrange(redis_key, 0, 0, withscores=True)
            reset_time = (
                datetime.fromtimestamp(
                    oldest_requests[0][1] + window_seconds,
                    tz=ZoneInfo("Asia/Ho_Chi_Minh"),
                )
                if oldest_requests
                else datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
            )

            return True, {
                "limit": limit,
                "remaining": limit - (current_count + 1),
                "reset_time": reset_time,
                "retry_after": None,
            }

        except redis.RedisError as e:
            raise Exception(f"Redis rate limiter error: {e}")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware"""

    def __init__(self, app, rate_limiter: Optional[RedisRateLimiter] = None):
        super().__init__(app)
        self.rate_limiter = rate_limiter or RedisRateLimiter()
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

        allowed, limit_info = self.rate_limiter.is_allowed(
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
        if request.url.path == "/health":
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

        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            try:
                token = auth_header.split(" ")[1]
                logger.info(f"Token: {token}")
                token_data = jwt_manager.verify_token(token)
                logger.info(f"Token data: {token_data}")
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
