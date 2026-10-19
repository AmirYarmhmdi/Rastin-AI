"""File guide.

- Use: Creates async SQLAlchemy session factories and request sessions.
- Usage: Import create_session_factory, get_async_session, and get_session_factory
  from rastin_ai.database.session.
- Duties: Defines create_session_factory, get_async_session, and get_session_factory
  and related helper logic.
- Depends on: Project modules: rastin_ai.database.engine.
"""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from rastin_ai.database.engine import get_engine


def create_session_factory(
    engine: AsyncEngine | None = None,
) -> async_sessionmaker[AsyncSession]:
    """Create an async SQLAlchemy session factory."""
    return async_sessionmaker(
        bind=engine or get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the cached application async session factory."""
    return create_session_factory()


async def get_async_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields one async database session."""
    async_session_factory = get_session_factory()
    async with async_session_factory() as session:
        yield session
