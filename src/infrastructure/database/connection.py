# src/infrastructure/database/connection.py

from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.core.config.settings import settings
from src.utils.logger_conf import logger

DEFAULT_MAX_KEY_LENGTH = 128
DEFAULT_MAX_VARCHAR_LENGTH = 256


class Base(AsyncAttrs, DeclarativeBase):
    pass


class DatabaseConnection:
    """Manages async database connections and sessions"""

    def __init__(self, db_url: str | None = None, auto_create_tables: bool = False):
        self.db_url = db_url or settings.database_url
        self.auto_create_tables = auto_create_tables
        self._initialized = False
        logger.info(f"Database URL: {self.db_url}")

        if self.db_url.startswith("postgresql://"):
            self.db_url = self.db_url.replace(
                "postgresql://", "postgresql+asyncpg://", 1
            )

        try:
            pool_config = {
                "pool_pre_ping": True,
                "pool_size": 5,
                "max_overflow": 10,
                "pool_timeout": 30,
                "pool_recycle": 1800,
                "echo": False,
            }

            connect_args = {}
            if "postgresql" in self.db_url:
                statement_timeout = 30000
                connect_args = {
                    "server_settings": {"statement_timeout": str(statement_timeout)}
                }

            self.engine: AsyncEngine = create_async_engine(
                self.db_url,
                **pool_config,
                connect_args=connect_args if connect_args else {},
            )
        except Exception as e:
            logger.error(f"Error creating async engine: {e}")
            raise e

        self.AsyncSessionLocal = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

    async def initialize(self):
        """Initialize the database connection and create tables if needed"""
        if not self._initialized:
            if self.auto_create_tables:
                async with self.engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
            self._initialized = True

    async def get_session(self) -> AsyncSession:
        """Get a new async database session"""
        await self.initialize()
        return self.AsyncSessionLocal()

    async def close(self):
        """Close the database connection"""
        await self.engine.dispose()
