# src/config/celery_app.py
from celery import Celery
# from src.tasks import file, qac  # noqa: F401

celery_app = Celery("kms-service")
celery_app.config_from_object("src.config.celery_config")
celery_app.autodiscover_tasks(["src.tasks"])
