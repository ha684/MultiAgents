# alembic/env.py

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from src.core.config.settings import settings
from src.infrastructure.database.connection import Base
from src.infrastructure.ssh.tunnel import (
    SSHTunnelManager,
    rewrite_database_url,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """
    Helper function that is run synchronously by connection.run_sync()
    to configure and run the Alembic context.
    """
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = None
    tunnel = None
    try:
        db_url = settings.database_url

        if getattr(settings, "use_ssh_tunnel", False):
            tunnel = SSHTunnelManager.from_settings(
                remote_host=settings.rds_host,
                remote_port=settings.rds_port,
            )
            local_port = await tunnel.start()

            db_url = rewrite_database_url(db_url, local_port)

        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

        connectable = create_async_engine(
            db_url,
            poolclass=pool.NullPool,
            connect_args={
                "timeout": 10,
                "command_timeout": 30,
                "ssl": "require",
            },
            echo=True,
        )

        async with connectable.connect() as connection:
            print("Database connected successfully! Running migrations...")
            await connection.run_sync(do_run_migrations)

    except Exception as e:
        import traceback

        traceback.print_exc()
        print("=" * 30 + "\n")
        raise e

    finally:
        if connectable:
            await connectable.dispose()

        if tunnel:
            print("Stopping SSH tunnel...")
            await tunnel.stop()
            print("SSH tunnel stopped.")
            tunnel = None


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
