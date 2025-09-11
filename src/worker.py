# worker.py
from src.config.celery_app import celery_app
from src.utils.logger_conf import logger

if __name__ == "__main__":
    logger.info("Starting optimized Celery worker for document processing")
    celery_app.worker_main(
        argv=[
            "worker",
            "--loglevel=info",
            "--pool=prefork",
            "--concurrency=4",
            "-Q",
            "document_processing",
            "--max-tasks-per-child=100",
            "--max-memory-per-child=200000",
            "-O",
            "fair",
            "--without-heartbeat",
            "--without-gossip",
            "--without-mingle",
        ]
    )
