# src/core/security/token.py

from datetime import datetime, timedelta
import hashlib
import hmac
import secrets
from zoneinfo import ZoneInfo

from src.core.config.settings import settings


class TokenManager:
    """Manage various types of tokens (verification, reset, etc.)"""

    @staticmethod
    def create_verification_token() -> tuple[str, datetime]:
        """Create an verification token with expiry"""
        token = f"{int(secrets.token_hex(4), 16) % 900000 + 100000}"
        expires_at = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")) + timedelta(
            minutes=settings.email_verification_token_expire_minutes
        )
        return token, expires_at

    @staticmethod
    def is_token_expired(expires_at: datetime) -> bool:
        """Check if a token has expired"""
        return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")) > expires_at

    @staticmethod
    def hash_token(token: str) -> str:
        """Hash a token for secure storage"""
        return hashlib.sha256(token.encode()).hexdigest()

    @staticmethod
    def verify_token_hash(token: str, token_hash: str) -> bool:
        """Verify a token against its hash"""
        return hmac.compare_digest(TokenManager.hash_token(token), token_hash)

    @staticmethod
    def generate_secure_token(length: int = 32) -> str:
        """Generate a cryptographically secure random token"""
        return secrets.token_urlsafe(length)
