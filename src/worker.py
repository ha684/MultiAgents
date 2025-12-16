# src/worker.py
from src.core.config.celery_app import celery_app
from src.utils.logger_conf import logger

if __name__ == "__main__":
    logger.info("Starting Celery worker")
    celery_app.worker_main(
        argv=[
            "worker",
            "--loglevel=info",
            "--pool=prefork",
            "--concurrency=2",
            "-Q",
            "document_processing,chat_inference,qa_generation",
            "--max-tasks-per-child=50",
            "--max-memory-per-child=200000",
            "-O",
            "fair",
        ]
    )
