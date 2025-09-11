from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from src.connector import database_connector
from src.utils.logger_conf import logger

class DatabaseSession:
    """Context manager for async database sessions"""
    
    def __init__(self):
        self.db_connection = database_connector
        self.session: Optional[AsyncSession] = None
    
    async def __aenter__(self) -> AsyncSession:
        self.session = await self.db_connection.get_session()
        return self.session
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            if exc_type is not None:
                await self.session.rollback()
                logger.error(f"Database session rolled back due to error: {exc_val}")
            else:
                await self.session.commit()
            await self.session.close()