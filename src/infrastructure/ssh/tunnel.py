# src/infrastructure/ssh/tunnel.py

import re
from dataclasses import dataclass
from typing import Optional

import asyncssh

from src.core.config.settings import settings
from src.utils.logger_conf import logger


@dataclass
class TunnelConfig:
    """Configuration for SSH tunnel"""

    ssh_host: str
    ssh_port: int
    ssh_username: str
    ssh_pkey_path: str
    remote_host: str
    remote_port: int


class SSHTunnelManager:
    """
    Manages async SSH tunnels using asyncssh.
    Supports port forwarding to remote services (RDS, ElastiCache, etc.)
    """

    def __init__(self, config: TunnelConfig):
        self.config = config
        self._connection: Optional[asyncssh.SSHClientConnection] = None
        self._listener: Optional[asyncssh.SSHListener] = None
        self._local_port: Optional[int] = None
        self._started = False

    @classmethod
    def from_settings(cls, remote_host: str, remote_port: int) -> "SSHTunnelManager":
        """Create SSHTunnelManager from application settings"""
        config = TunnelConfig(
            ssh_host=settings.ssh_host,
            ssh_port=settings.ssh_port,
            ssh_username=settings.ssh_username,
            ssh_pkey_path=settings.ssh_pkey_path,
            remote_host=remote_host,
            remote_port=remote_port,
        )
        return cls(config)

    @property
    def local_port(self) -> Optional[int]:
        """Get the local port of the tunnel"""
        return self._local_port

    @property
    def local_bind_address(self) -> tuple[str, int]:
        """Get the local bind address (host, port)"""
        return ("127.0.0.1", self._local_port)

    @property
    def is_active(self) -> bool:
        """Check if the tunnel is active"""
        return self._started and self._connection is not None

    async def start(self) -> int:
        """
        Start the SSH tunnel and return the local port.

        Returns:
            int: The local port that the tunnel is listening on
        """
        if self._started:
            logger.warning("SSH tunnel is already started")
            return self._local_port

        try:
            logger.info(
                f"Setting up SSH tunnel via {self.config.ssh_host}:{self.config.ssh_port} "
                f"-> {self.config.remote_host}:{self.config.remote_port}"
            )

            # Connect to SSH server
            self._connection = await asyncssh.connect(
                host=self.config.ssh_host,
                port=self.config.ssh_port,
                username=self.config.ssh_username,
                client_keys=[self.config.ssh_pkey_path],
                known_hosts=None,  # Disable host key checking
            )

            # Create port forwarding
            self._listener = await self._connection.forward_local_port(
                listen_host="127.0.0.1",
                listen_port=0,  # Auto-assign port
                dest_host=self.config.remote_host,
                dest_port=self.config.remote_port,
            )

            self._local_port = self._listener.get_port()
            self._started = True

            logger.info(f"SSH tunnel started on local port: {self._local_port}")
            return self._local_port

        except Exception as e:
            logger.error(f"Failed to setup SSH tunnel: {e}")
            await self.stop()
            raise

    async def stop(self):
        """Stop the SSH tunnel and clean up resources"""
        if self._listener:
            logger.info("Closing SSH listener")
            self._listener.close()
            try:
                await self._listener.wait_closed()
            except Exception as e:
                logger.warning(f"Error closing SSH listener: {e}")
            self._listener = None

        if self._connection:
            logger.info("Closing SSH connection")
            self._connection.close()
            try:
                await self._connection.wait_closed()
            except Exception as e:
                logger.warning(f"Error closing SSH connection: {e}")
            self._connection = None

        self._local_port = None
        self._started = False
        logger.info("SSH tunnel stopped")

    async def __aenter__(self) -> "SSHTunnelManager":
        """Async context manager entry"""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.stop()


def rewrite_database_url(original_url: str, local_port: int) -> str:
    """
    Rewrite database URL to use local tunnel port.

    Args:
        original_url: Original database URL (postgresql+asyncpg://user:pass@host:port/db)
        local_port: Local tunnel port to use

    Returns:
        Updated database URL pointing to localhost:local_port
    """
    pattern = r"postgresql\+asyncpg://([^:]+):([^@]+)@[^/]+/(.+)"
    match = re.match(pattern, original_url)

    if match:
        username, password, database = match.groups()
        new_url = f"postgresql+asyncpg://{username}:{password}@127.0.0.1:{local_port}/{database}"
        logger.info(
            f"Rewrote DB URL: postgresql+asyncpg://{username}:***@127.0.0.1:{local_port}/{database}"
        )
        return new_url

    logger.warning(f"Could not parse database URL for tunnel rewrite: {original_url}")
    return original_url


def rewrite_redis_url(original_url: str, local_port: int, use_ssl: bool = True) -> str:
    """
    Rewrite Redis URL to use local tunnel port.

    Args:
        original_url: Original Redis URL (redis://[:password@]host:port[/db])
        local_port: Local tunnel port to use
        use_ssl: Whether to use SSL (rediss://)

    Returns:
        Updated Redis URL pointing to localhost:local_port
    """
    # Parse: redis://[:password@]host:port[/db] or rediss://...
    pattern = r"rediss?://(?::([^@]+)@)?[^/]+(/.+)?"
    match = re.match(pattern, original_url)

    password_part = ""
    db_part = "/0"

    if match:
        password = match.group(1)
        db = match.group(2)

        if password:
            password_part = f":{password}@"
        if db:
            db_part = db

    scheme = "rediss" if use_ssl else "redis"
    new_url = f"{scheme}://{password_part}127.0.0.1:{local_port}{db_part}"

    logger.info(f"Rewrote Redis URL: {scheme}://***@127.0.0.1:{local_port}{db_part}")
    return new_url
