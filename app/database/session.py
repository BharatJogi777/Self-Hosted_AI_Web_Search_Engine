import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def get_database_url() -> str:
    return os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://search:search@localhost:5432/search_engine",
    )


def create_session_factory(database_url: str | None = None) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory for the application or tests."""
    engine = create_async_engine(database_url or get_database_url(), pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)
