# src/middleware/rate_limiting.py
import time
from typing import Dict, Optional, Callable, Any, Tuple
from datetime import datetime, timedelta, timezone
from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import redis
from src.config.auth_settings import RATE_LIMIT_CONFIG
from src.exceptions.auth_exceptions import RateLimitExceededException
from src.utils.logger_conf import logger
from dotenv import load_dotenv
import os

load_dotenv()


class RedisRateLimiter:
    """Redis-based rate limiter for production use"""

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

        # Use Redis pipeline for atomic operations
        pipe = self.redis.pipeline()

        try:
            # Remove expired entries (outside the window)
            pipe.zremrangebyscore(redis_key, 0, now - window_seconds)

            # Count current requests in window
            pipe.zcard(redis_key)

            # Execute pipeline
            results = pipe.execute()
            current_count = results[1]

            # Check if limit exceeded
            if current_count >= limit:
                # Get oldest request timestamp to calculate retry_after
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
                        oldest_time + window_seconds, tz=timezone.utc
                    )
                    if oldest_requests
                    else datetime.now(timezone.utc),
                    "retry_after": retry_after,
                }

            # Add current request with score as timestamp
            # Use microseconds for uniqueness in case of concurrent requests
            unique_score = now + (time.time_ns() % 1000000) / 1000000000
            self.redis.zadd(redis_key, {str(unique_score): unique_score})

            # Set expiration for the key (cleanup)
            self.redis.expire(redis_key, window_seconds + 1)

            # Get reset time (when oldest request will expire)
            oldest_requests = self.redis.zrange(redis_key, 0, 0, withscores=True)
            reset_time = (
                datetime.fromtimestamp(
                    oldest_requests[0][1] + window_seconds, tz=timezone.utc
                )
                if oldest_requests
                else datetime.now(timezone.utc)
            )

            return True, {
                "limit": limit,
                "remaining": limit - (current_count + 1),
                "reset_time": reset_time,
                "retry_after": None,
            }

        except redis.RedisError as e:
            # Fallback behavior on Redis error - you might want to allow or deny
            # depending on your requirements
            raise Exception(f"Redis rate limiter error: {e}")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware"""

    def __init__(self, app, rate_limiter: Optional[RedisRateLimiter] = None):
        super().__init__(app)
        self.rate_limiter = rate_limiter or RedisRateLimiter()
        self.config = RATE_LIMIT_CONFIG

        # Route-specific configurations
        self.route_configs = {
            "/auth/login": self.config["auth"],
            "/auth/register": self.config["auth"],
            "/auth/password/reset": self.config["password_reset"],
            "/auth/password/reset/confirm": self.config["password_reset"],
        }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process rate limiting for requests"""

        # Skip rate limiting for certain paths
        if self._should_skip_rate_limiting(request):
            return await call_next(request)

        # Get rate limit configuration for this route
        rate_config = self._get_rate_config(request)
        if not rate_config:
            return await call_next(request)

        # Create rate limit key
        rate_limit_key = self._create_rate_limit_key(request)

        # Check rate limit
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

        # Process request
        response = await call_next(request)

        # Add rate limit headers to successful responses
        if hasattr(response, "headers"):
            response.headers["X-RateLimit-Limit"] = str(limit_info["limit"])
            response.headers["X-RateLimit-Remaining"] = str(limit_info["remaining"])
            response.headers["X-RateLimit-Reset"] = str(
                int(limit_info["reset_time"].timestamp())
            )

        return response

    def _should_skip_rate_limiting(self, request: Request) -> bool:
        """Check if rate limiting should be skipped for this request"""
        # Skip for health checks
        if request.url.path == "/health":
            return True

        # Skip for websocket connections
        if (
            request.url.path.startswith("/ws/")
            or request.url.path.startswith("/websocket/")
            or request.headers.get("upgrade", "").lower() == "websocket"
        ):
            return True

        # Skip for OPTIONS requests (CORS preflight)
        if request.method == "OPTIONS":
            return True

        return False

    def _get_rate_config(self, request: Request) -> Optional[dict]:
        """Get rate limit configuration for the current route"""
        path = request.url.path

        # Check for exact path match
        if path in self.route_configs:
            return self.route_configs[path]

        # Check for path prefixes
        for route_path, config in self.route_configs.items():
            if path.startswith(route_path.rstrip("*")):
                return config

        # Use default configuration
        return self.config["default"]

    def _create_rate_limit_key(self, request: Request) -> str:
        """Create rate limit key for the request"""
        # Get client IP
        client_ip = self._get_client_ip(request)

        # For authenticated routes, use user ID if available
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            try:
                from src.utils.security import jwt_manager

                token = auth_header.split(" ")[1]
                token_data = jwt_manager.verify_token(token)
                if token_data:
                    return f"user:{token_data.user_id}:{request.url.path}"
            except Exception:
                pass  # Fall back to IP-based limiting

        # Use IP-based limiting
        return f"ip:{client_ip}:{request.url.path}"

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address from request"""
        # Check for forwarded IP (when behind proxy/load balancer)
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # Take the first IP in case of multiple proxies
            return forwarded_for.split(",")[0].strip()

        # Check for real IP header
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        # Fall back to direct connection IP
        return request.client.host if request.client else "unknown"


# Decorator for applying rate limits to specific endpoints
def rate_limit(requests: int, window_minutes: int):
    """Decorator to apply rate limiting to specific endpoints"""

    def decorator(func):
        # Store rate limit config on the function
        func._rate_limit_config = {
            "requests": requests,
            "window": timedelta(minutes=window_minutes),
        }
        return func

    return decorator


# Utility function to check rate limits in endpoints
async def check_rate_limit(
    request: Request,
    identifier: str,
    limit: int,
    window_minutes: int,
    rate_limiter: Optional[RedisRateLimiter] = None,
) -> None:
    """Manual rate limit check for use in endpoints"""
    limiter = rate_limiter or RedisRateLimiter()

    key = f"manual:{identifier}:{request.url.path}"
    allowed, limit_info = limiter.is_allowed(key, limit, window_minutes * 60)

    if not allowed:
        raise RateLimitExceededException(
            detail=f"Rate limit exceeded. Try again in {limit_info['retry_after']} seconds",
            retry_after=limit_info["retry_after"],
        )
