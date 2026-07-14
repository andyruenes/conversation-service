# FIXED: shared-async-url, Connection-type-hint, import-order
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app.config import normalize_database_url_for_asyncpg, settings
from app.models.base import Base
from app.models.cost import CostModel, TokenPriceModel  # noqa: F401
from app.models.message import MessageModel  # noqa: F401
from app.models.session import SessionModel  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_async_database_url() -> str:
    return normalize_database_url_for_asyncpg(settings.DATABASE_URL)


def run_migrations_offline() -> None:
    url: str = get_async_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in an async engine (asyncpg)."""
    url = get_async_database_url()
    connectable = create_async_engine(url, poolclass=pool.NullPool)

    async with connectable.begin() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
