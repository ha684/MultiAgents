# src/infrastructure/email/__init__.py

from src.core.config.settings import settings
from src.infrastructure.email.gmail_client import GmailAPI

gmail_api = GmailAPI(
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    refresh_token=settings.google_refresh_token,
)
