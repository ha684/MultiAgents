# src/database/repositories/refresh_token_repository.py
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import and_, delete, update
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from src.core.exceptions.auth_exceptions import DatabaseException
from src.database.models.user import RefreshToken
from src.dependencies.database_session import DatabaseSession
from src.utils.logger_conf import logger


class RefreshTokenRepository:
    """Refresh token database operations"""

    async def create_refresh_token(
        self,
        user_id: str,
        token_hash: str,
        expires_at: datetime,
    ) -> RefreshToken:
        """Create a new refresh token"""
        try:
            refresh_token = RefreshToken(
                user_id=uuid.UUID(user_id),
                token_hash=token_hash,
                expires_at=expires_at,
                created_at=datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")),
            )

            async with DatabaseSession() as session:
                session.add(refresh_token)
                await session.flush()
                await session.refresh(refresh_token)

            return refresh_token
        except Exception as e:
            logger.error(f"Error creating refresh token: {str(e)}")
            raise DatabaseException("Failed to create refresh token")

    async def get_refresh_token(self, token_hash: str) -> RefreshToken | None:
        """Get refresh token by hash"""
        try:
            async with DatabaseSession() as session:
                result = await session.execute(
                    select(RefreshToken)
                    .options(selectinload(RefreshToken.user))
                    .where(
                        and_(
                            RefreshToken.token_hash == token_hash,
                            not RefreshToken.is_revoked,
                            RefreshToken.expires_at
                            > datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")),
                        )
                    )
                )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting refresh token: {str(e)}")
            raise DatabaseException("Failed to retrieve refresh token")

    async def revoke_refresh_token(self, token_hash: str) -> bool:
        """Revoke a refresh token"""
        try:
            async with DatabaseSession() as session:
                stmt = (
                    update(RefreshToken)
                    .where(RefreshToken.token_hash == token_hash)
                    .values(
                        is_revoked=True,
                        revoked_at=datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")),
                    )
                    .returning(RefreshToken)
                )
                result = await session.execute(stmt)
                await session.commit()

            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error revoking refresh token: {str(e)}")
            raise DatabaseException("Failed to revoke refresh token")

    async def revoke_all_user_tokens(self, user_id: str) -> int:
        """Revoke all refresh tokens for a user"""
        try:
            async with DatabaseSession() as session:
                stmt = (
                    update(RefreshToken)
                    .where(RefreshToken.user_id == uuid.UUID(user_id))
                    .values(
                        is_revoked=True,
                        revoked_at=datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")),
                    )
                    .returning(RefreshToken)
                )
                result = await session.execute(stmt)
                await session.commit()

            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error revoking all user tokens: {str(e)}")
            raise DatabaseException("Failed to revoke user tokens")

    async def cleanup_expired_tokens(self) -> int:
        """Clean up expired refresh tokens"""
        try:
            async with DatabaseSession() as session:
                stmt = (
                    delete(RefreshToken)
                    .where(
                        RefreshToken.expires_at
                        < datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
                    )
                    .returning(RefreshToken)
                )
                result = await session.execute(stmt)
                await session.commit()

            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error cleaning up expired tokens: {str(e)}")
            raise DatabaseException("Failed to cleanup expired tokens")
