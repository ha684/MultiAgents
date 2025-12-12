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
from src.infrastructure.ssh.tunnel import SSHTunnelManager, rewrite_database_url
from src.utils.logger_conf import logger

DEFAULT_MAX_KEY_LENGTH = 128
DEFAULT_MAX_VARCHAR_LENGTH = 256


class Base(AsyncAttrs, DeclarativeBase):
    pass


class DatabaseConnection:
    """Manages async database connections and sessions with SSH tunnel support"""

    def __init__(self, db_url: str | None = None, auto_create_tables: bool = False):
        self.db_url = db_url or settings.database_url
        self.auto_create_tables = auto_create_tables
        self._initialized = False
        self._ssh_tunnel: SSHTunnelManager | None = None

        # SSH tunnel configuration
        self.use_ssh_tunnel = getattr(settings, "use_ssh_tunnel", False)

        # RDS configuration
        self.rds_host = getattr(settings, "rds_host", None)
        self.rds_port = getattr(settings, "rds_port", 5432)

        logger.info(f"Database URL: {self.db_url}")
        logger.info(f"Use SSH Tunnel: {self.use_ssh_tunnel}")

    async def _setup_ssh_tunnel(self):
        """Setup SSH tunnel using asyncssh"""
        if self._ssh_tunnel and self._ssh_tunnel.is_active:
            logger.warning("SSH tunnel is already active")
            return

        self._ssh_tunnel = SSHTunnelManager.from_settings(
            remote_host=self.rds_host,
            remote_port=self.rds_port,
        )

        local_port = await self._ssh_tunnel.start()

        # Rewrite database URL to use tunnel
        self.db_url = rewrite_database_url(self.db_url, local_port)

    def _create_engine(self):
        """Create SQLAlchemy async engine"""
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
                    "server_settings": {"statement_timeout": str(statement_timeout)},
                    "ssl": "require",  # Enable SSL for RDS
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
            # Setup SSH tunnel if enabled (async)
            if self.use_ssh_tunnel and not self._ssh_tunnel:
                await self._setup_ssh_tunnel()

            # Create engine after tunnel is ready
            if not hasattr(self, "engine"):
                self._create_engine()

            if self.auto_create_tables:
                async with self.engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)

            self._initialized = True

    async def get_session(self) -> AsyncSession:
        """Get a new async database session"""
        await self.initialize()
        return self.AsyncSessionLocal()

    async def close(self):
        """Close the database connection and SSH tunnel"""
        if hasattr(self, "engine"):
            await self.engine.dispose()

        if self._ssh_tunnel:
            await self._ssh_tunnel.stop()
            self._ssh_tunnel = None
