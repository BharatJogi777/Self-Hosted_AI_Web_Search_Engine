from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.jobs import CrawlJob
from app.database.queue import CrawlJobRepository


@pytest.mark.asyncio
async def test_enqueue_and_get_active_job():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    repository = CrawlJobRepository(sessions)

    first = await repository.enqueue("https://example.com/")
    duplicate = await repository.enqueue("https://example.com/")
    loaded = await repository.get(first.id)

    assert first.id == duplicate.id
    assert loaded is not None
    assert loaded.status == "pending"
    assert loaded.attempts == 0
    assert loaded.max_attempts == 5

    await engine.dispose()


@pytest.mark.asyncio
async def test_completed_job_does_not_block_future_recrawl():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    repository = CrawlJobRepository(sessions)

    first = await repository.enqueue("https://example.com/")
    async with sessions() as session:
        async with session.begin():
            job = await session.get(CrawlJob, first.id)
            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)

    second = await repository.enqueue("https://example.com/")
    assert second.id != first.id

    await engine.dispose()
