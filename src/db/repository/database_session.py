from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from src.connector import database_connector
from src.utils.logger_conf import logger


class DatabaseConnectionError(Exception):
    """Raised when database connection fails"""

    def __init__(self, message: str = "Database connection failed"):
        self.message = message
        super().__init__(self.message)


class DatabaseTransactionError(Exception):
    """Raised when database transaction fails"""

    def __init__(self, message: str = "Database transaction failed"):
        self.message = message
        super().__init__(self.message)


class DatabaseSession:
    """Context manager for async database sessions"""

    def __init__(self):
        self.db_connection = database_connector
        self.session: Optional[AsyncSession] = None

    async def __aenter__(self) -> AsyncSession:
        try:
            self.session = await self.db_connection.get_session()
            if not self.session:
                raise DatabaseConnectionError("Failed to get database session")
            return self.session

        except SQLAlchemyError as e:
            logger.error(f"Database connection error: {e}")
            raise DatabaseConnectionError(f"Database connection failed: {str(e)}")

        except Exception as e:
            logger.error(f"Unexpected error getting database session: {e}")
            raise DatabaseConnectionError(
                f"Unexpected database connection error: {str(e)}"
            )

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if not self.session:
            return

        try:
            if exc_type is not None:
                await self.session.rollback()
                logger.error(f"Database session rolled back due to error: {exc_val}")
            else:
                await self.session.commit()
                logger.debug("Database session committed successfully")

        except SQLAlchemyError as e:
            logger.error(
                f"Database transaction error during {'rollback' if exc_type else 'commit'}: {e}"
            )
            try:
                await self.session.rollback()
            except Exception:
                pass
            raise DatabaseTransactionError(f"Transaction failed: {str(e)}")

        except Exception as e:
            logger.error(f"Unexpected error during session cleanup: {e}")
            try:
                await self.session.rollback()
            except Exception:
                pass
            raise DatabaseTransactionError(f"Session cleanup failed: {str(e)}")

        finally:
            try:
                await self.session.close()
                logger.debug("Database session closed")
            except Exception as e:
                logger.error(f"Error closing database session: {e}")
