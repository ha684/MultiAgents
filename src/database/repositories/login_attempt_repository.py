# src/database/repositories/login_attempt_repository.py
from datetime import datetime
from zoneinfo import ZoneInfo

from src.database.models.user import LoginAttempt
from src.dependencies.database_session import DatabaseSession
from src.utils.logger_conf import logger


class LoginAttemptRepository:
    """Login attempt tracking"""

    async def record_login_attempt(
        self,
        email: str,
        success: bool,
        failure_reason: str | None = None,
    ) -> LoginAttempt:
        """Record a login attempt"""
        try:
            attempt = LoginAttempt(
                email=email.lower(),
                success=success,
                failure_reason=failure_reason,
                attempted_at=datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")),
            )

            async with DatabaseSession() as session:
                session.add(attempt)
                await session.flush()

            return attempt
        except Exception as e:
            logger.error(f"Error recording login attempt: {str(e)}")
