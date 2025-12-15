# src/streaming_worker.py
"""
Celery worker for LLM streaming tasks.

This worker processes the llm_streaming queue and produces events to Kafka.
"""

from src.core.config.celery_app import celery_app
from src.utils.logger_conf import logger

if __name__ == "__main__":
    logger.info("Starting Celery streaming worker")
    celery_app.worker_main(
        argv=[
            "worker",
            "--loglevel=info",
            "--pool=prefork",
            "--concurrency=4",  # More workers for streaming
            "-Q",
            "llm_streaming",
            "--max-tasks-per-child=50",
            "--max-memory-per-child=300000",  # 300MB per child
            "-O",
            "fair",
            "--without-heartbeat",
            "--without-gossip",
            "--without-mingle",
        ]
    )
