# src/middlewares/endpoint_manager.py
import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from functools import wraps
from typing import Any

from fastapi import HTTPException

from src.utils.logger_conf import logger


@dataclass
class EndpointProtectionConfig:
    """Simple configuration for endpoint protection - no user tracking needed"""

    endpoint_name: str
    max_concurrent: int = 50  # Max concurrent requests processing
    max_queue_size: int = 200  # Max requests waiting in queue
    queue_timeout: int = 120  # Timeout for queued requests (seconds)
    processing_timeout: int = 300  # Timeout for processing (seconds)


class EndpointStats:
    """Simple stats tracking for endpoint"""

    def __init__(self):
        self.total_requests = 0
        self.completed_requests = 0
        self.rejected_requests = 0
        self.timeout_requests = 0
        self.current_processing = 0
        self.current_queued = 0
        self.queue_wait_times = []


class EndpointProtector:
    """Simple endpoint protector - focus only on system capacity"""

    def __init__(self, config: EndpointProtectionConfig):
        self.config = config
        self.stats = EndpointStats()
        self.processing_semaphore = asyncio.Semaphore(config.max_concurrent)
        self.request_queue = asyncio.Queue(maxsize=config.max_queue_size)
        self.workers_started = False
        logger.info(f"EndpointProtector created for {config.endpoint_name}")

    async def start_workers(self):
        """Start background workers to process queue"""
        if not self.workers_started:
            for i in range(self.config.max_concurrent):
                asyncio.create_task(
                    self._worker(f"{self.config.endpoint_name}-worker-{i}")
                )
            self.workers_started = True
            logger.info(
                f"Started {self.config.max_concurrent} workers for {self.config.endpoint_name}"
            )

    async def _worker(self, worker_name: str):
        """Background worker - processes requests from queue"""
        while True:
            try:
                request_item = await self.request_queue.get()
                queue_wait_time = (
                    datetime.now() - request_item["queued_at"]
                ).total_seconds()

                if queue_wait_time > self.config.queue_timeout:
                    self.stats.timeout_requests += 1
                    request_item["future"].set_exception(
                        HTTPException(
                            status_code=408, detail="Request timeout in queue"
                        )
                    )
                    self.request_queue.task_done()
                    continue

                async with self.processing_semaphore:
                    self.stats.current_processing += 1

                    try:
                        logger.info(
                            f"{worker_name} processing after {queue_wait_time:.1f}s queue wait"
                        )

                        handler_func = request_item["handler_func"]
                        args = request_item["args"]
                        kwargs = request_item["kwargs"]

                        result = await asyncio.wait_for(
                            handler_func(*args, **kwargs),
                            timeout=self.config.processing_timeout,
                        )

                        request_item["future"].set_result(result)
                        self.stats.completed_requests += 1
                        self.stats.queue_wait_times.append(queue_wait_time)

                        if len(self.stats.queue_wait_times) > 1000:
                            self.stats.queue_wait_times = self.stats.queue_wait_times[
                                -500:
                            ]

                    except TimeoutError:
                        request_item["future"].set_exception(
                            HTTPException(status_code=504, detail="Processing timeout")
                        )
                    except Exception as e:
                        request_item["future"].set_exception(e)
                    finally:
                        self.stats.current_processing -= 1
                        self.request_queue.task_done()

            except Exception as e:
                logger.error(f"Worker {worker_name} error: {e}")
                await asyncio.sleep(1)

    async def protect_request(self, handler_func: Callable, *args, **kwargs) -> Any:
        """
        Protect endpoint request - main entry point
        No user tracking, just system capacity protection
        """
        self.stats.total_requests += 1
        if self.request_queue.qsize() >= self.config.max_queue_size:
            self.stats.rejected_requests += 1
            raise HTTPException(
                status_code=503,
                detail=f"Endpoint {self.config.endpoint_name} overloaded. Queue full ({self.config.max_queue_size}).",
                headers={"Retry-After": "30"},
            )

        request_id = str(uuid.uuid4())[:8]
        future = asyncio.Future()

        request_item = {
            "request_id": request_id,
            "future": future,
            "queued_at": datetime.now(),
            "handler_func": handler_func,
            "args": args,
            "kwargs": kwargs,
        }

        try:
            self.request_queue.put_nowait(request_item)
            self.stats.current_queued += 1

            estimated_wait = self.request_queue.qsize() * (
                sum(self.stats.queue_wait_times[-10:])
                / min(10, len(self.stats.queue_wait_times))
                if self.stats.queue_wait_times
                else 30
            )

            logger.info(
                f"Request {request_id} queued for {self.config.endpoint_name}. "
                f"Position: {self.request_queue.qsize()}, Est. wait: {estimated_wait:.0f}s"
            )

            result = await asyncio.wait_for(
                future, timeout=self.config.queue_timeout + 60
            )
            return result

        except TimeoutError:
            self.stats.timeout_requests += 1
            raise HTTPException(status_code=408, detail="Request timed out")
        finally:
            if self.stats.current_queued > 0:
                self.stats.current_queued -= 1

    def get_health_status(self) -> dict[str, Any]:
        """Get endpoint health status"""
        queue_size = self.request_queue.qsize()
        processing_utilization = (
            self.stats.current_processing / self.config.max_concurrent
        ) * 100
        queue_utilization = (queue_size / self.config.max_queue_size) * 100

        if queue_utilization >= 90:
            status = "critical"
        elif queue_utilization >= 70:
            status = "overloaded"
        elif processing_utilization >= 80:
            status = "high_load"
        else:
            status = "healthy"

        avg_wait = (
            sum(self.stats.queue_wait_times[-100:])
            / min(100, len(self.stats.queue_wait_times))
            if self.stats.queue_wait_times
            else 0
        )

        return {
            "endpoint_name": self.config.endpoint_name,
            "status": status,
            "capacity": {
                "processing": f"{self.stats.current_processing}/{self.config.max_concurrent}",
                "processing_utilization_percent": processing_utilization,
                "queue": f"{queue_size}/{self.config.max_queue_size}",
                "queue_utilization_percent": queue_utilization,
            },
            "performance": {
                "avg_queue_wait_seconds": avg_wait,
                "estimated_wait_seconds": queue_size * (avg_wait or 30),
            },
            "stats": {
                "total_requests": self.stats.total_requests,
                "completed_requests": self.stats.completed_requests,
                "rejected_requests": self.stats.rejected_requests,
                "timeout_requests": self.stats.timeout_requests,
                "success_rate_percent": (
                    (self.stats.completed_requests / max(self.stats.total_requests, 1))
                    * 100
                ),
            },
        }


class EndpointManager:
    """Manager for all protected endpoints"""

    def __init__(self):
        self.protectors: dict[str, EndpointProtector] = {}

    def register_endpoint(self, config: EndpointProtectionConfig) -> EndpointProtector:
        """Register endpoint for protection"""
        if config.endpoint_name in self.protectors:
            logger.warning(f"Endpoint {config.endpoint_name} already registered")

        protector = EndpointProtector(config)
        self.protectors[config.endpoint_name] = protector
        return protector

    def get_protector(self, endpoint_name: str) -> EndpointProtector | None:
        """Get protector for endpoint"""
        return self.protectors.get(endpoint_name)

    async def start_all_workers(self):
        """Start workers for all endpoints"""
        for protector in self.protectors.values():
            await protector.start_workers()

    def get_global_health(self) -> dict[str, Any]:
        """Get health for all endpoints"""
        return {
            name: protector.get_health_status()
            for name, protector in self.protectors.items()
        }


endpoint_manager = EndpointManager()


def endpoint_protection(
    endpoint_name: str,
    max_concurrent: int = 50,
    max_queue_size: int = 200,
    queue_timeout: int = 120,
    processing_timeout: int = 300,
):
    """
    Decorator for endpoint protection - simplified version
    Only protects system capacity, no user tracking
    """

    def decorator(func: Callable) -> Callable:
        config = EndpointProtectionConfig(
            endpoint_name=endpoint_name,
            max_concurrent=max_concurrent,
            max_queue_size=max_queue_size,
            queue_timeout=queue_timeout,
            processing_timeout=processing_timeout,
        )
        protector = endpoint_manager.register_endpoint(config)

        @wraps(func)
        async def wrapper(*args, **kwargs):
            await protector.start_workers()
            return await protector.protect_request(func, *args, **kwargs)

        return wrapper

    return decorator
