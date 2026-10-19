"""File guide.

- Use: Configures Alembic so migrations can use the app database metadata.
- Usage: Alembic imports this file when creating or running migrations.
- Duties: Defines do_run_migrations, run_async_migrations, run_migrations_offline,
  and run_migrations_online and related helper logic.
- Depends on: Project modules: rastin_ai.database, rastin_ai.database.base,
  and rastin_ai.database.engine.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from rastin_ai.database import models  # noqa: F401
from rastin_ai.database.base import Base
from rastin_ai.database.engine import get_database_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def escape_database_url_for_config_parser(database_url: str) -> str:
    """Escape percent signs before storing URLs in Alembic's ConfigParser."""
    return database_url.replace("%", "%%")


def run_migrations_offline() -> None:
    """Run migrations without a live database connection."""
    url = get_database_url()
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
    """Run migrations with SQLAlchemy's async engine."""
    config.set_main_option(
        "sqlalchemy.url",
        escape_database_url_for_config_parser(get_database_url()),
    )
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
