"""
Database models for the application using SQLAlchemy with async support
"""

from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
    AsyncEngine,
)
from src.config.settings import settings
from src.utils.logger_conf import logger

DEFAULT_MAX_KEY_LENGTH = 128
DEFAULT_MAX_VARCHAR_LENGTH = 256


class Base(AsyncAttrs, DeclarativeBase):
    pass


class DatabaseConnection:
    """Manages async database connections and sessions"""

    def __init__(self, db_url: str, auto_create_tables: bool = True):
        self.db_url = db_url or settings.database_url
        self.auto_create_tables = auto_create_tables
        self._initialized = False
        logger.info(f"Database URL: {self.db_url}")

        if self.db_url.startswith("postgresql://"):
            self.db_url = self.db_url.replace(
                "postgresql://", "postgresql+asyncpg://", 1
            )
        elif self.db_url.startswith("mysql://"):
            self.db_url = self.db_url.replace("mysql://", "mysql+aiomysql://", 1)
        elif self.db_url.startswith("sqlite://"):
            self.db_url = self.db_url.replace("sqlite://", "sqlite+aiosqlite://", 1)

        try:
            pool_config = {
                "pool_pre_ping": True,
                "pool_size": 5,  # Start with 5 persistent connections
                "max_overflow": 10,  # Allow 10 additional when needed
                "pool_timeout": 30,  # Good
                "pool_recycle": 1800,  # Good
                "echo": False,  # Good
            }

            connect_args = {}
            if "postgresql" in self.db_url:
                statement_timeout = (
                    settings.database_statement_timeout
                    if hasattr(settings, "database_statement_timeout")
                    else 30000
                )
                connect_args = {
                    "server_settings": {"statement_timeout": str(statement_timeout)}
                }

            self.engine: AsyncEngine = create_async_engine(
                settings.get_database_url_with_ssl()
                if hasattr(settings, "database_ssl_required")
                else self.db_url,
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
                await self._create_tables_async()
            self._initialized = True

    async def _create_tables_async(self):
        """Internal method to create tables automatically"""
        try:
            await self.create_tables()
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Error creating database tables: {e}")
            raise e

    async def create_tables(self):
        """Create all tables - can be called manually if needed"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def get_session(self) -> AsyncSession:
        """Get a new async database session"""
        await self.initialize()
        return self.AsyncSessionLocal()

    async def close(self):
        """Close the database connection"""
        await self.engine.dispose()
