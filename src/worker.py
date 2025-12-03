# src/worker.py
from src.core.config.celery_app import celery_app
from src.utils.logger_conf import logger

if __name__ == "__main__":
    logger.info("Starting Celery worker (Low Resource Mode)")
    celery_app.worker_main(
        argv=[
            "worker",
            "--loglevel=info",
            "--pool=prefork",
            "--concurrency=1",
            "-Q",
            "document_processing",
            "--max-tasks-per-child=20",
            "--max-memory-per-child=100000",
            "-O",
            "fair",
            "--without-heartbeat",
            "--without-gossip",
            "--without-mingle",
        ]
    )
