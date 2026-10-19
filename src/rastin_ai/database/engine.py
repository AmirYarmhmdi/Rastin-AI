"""File guide.

- Use: Builds async database engines from application settings.
- Usage: Import create_database_engine, get_database_url, and get_engine from
  rastin_ai.database.engine.
- Duties: Defines create_database_engine, get_database_url, and get_engine and
  related helper logic.
- Depends on: Project modules: rastin_ai.core.config.
"""

from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from rastin_ai.core.config import Settings, get_settings


def get_database_url(settings: Settings | None = None) -> str:
    """Return the configured async PostgreSQL database URL."""
    resolved_settings = settings or get_settings()
    if not resolved_settings.DATABASE_URL:
        msg = "DATABASE_URL must be set before opening database connections."
        raise RuntimeError(msg)

    return resolved_settings.DATABASE_URL


def create_database_engine(database_url: str | None = None) -> AsyncEngine:
    """Create an async SQLAlchemy engine for PostgreSQL."""
    return create_async_engine(
        database_url or get_database_url(),
        pool_pre_ping=True,
    )


@lru_cache
def get_engine(database_url: str | None = None) -> AsyncEngine:
    """Return a cached async engine for the configured database."""
    return create_database_engine(database_url)


async def dispose_engine() -> None:
    """Dispose the cached database engine when one has been created."""
    if get_engine.cache_info().currsize == 0:
        return

    engine = get_engine()
    await engine.dispose()
    get_engine.cache_clear()
