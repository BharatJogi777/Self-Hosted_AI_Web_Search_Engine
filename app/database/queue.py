from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.jobs import CrawlJob


@dataclass(frozen=True)
class ClaimedJob:
    id: uuid.UUID
    url: str
    attempts: int
    max_attempts: int


class CrawlJobRepository:
    """PostgreSQL-backed queue using leases and SKIP LOCKED claims."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def enqueue(self, url: str, max_attempts: int = 5) -> CrawlJob:
        now = datetime.now(timezone.utc)
        async with self.sessions() as session:
            async with session.begin():
                existing = await session.scalar(
                    select(CrawlJob).where(
                        CrawlJob.url == url,
                        CrawlJob.status.in_(("pending", "running")),
                    ).limit(1)
                )
                if existing is not None:
                    return existing
                job = CrawlJob(
                    url=url,
                    status="pending",
                    attempts=0,
                    max_attempts=max_attempts,
                    available_at=now,
                )
                session.add(job)
                await session.flush()
                return job

    async def claim(self, worker_id: str, lease_seconds: int = 60) -> ClaimedJob | None:
        """Atomically claim one available or lease-expired job."""
        statement = text("""
            WITH candidate AS (
                SELECT id
                FROM crawl_jobs
                WHERE (
                    (status = 'pending' AND available_at <= :now)
                    OR (status = 'running' AND locked_until < :now)
                )
                AND attempts < max_attempts
                ORDER BY available_at, created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE crawl_jobs AS job
            SET status = 'running',
                attempts = job.attempts + 1,
                locked_by = :worker_id,
                locked_until = :lease_until,
                updated_at = :now
            FROM candidate
            WHERE job.id = candidate.id
            RETURNING job.id, job.url, job.attempts, job.max_attempts
        """)
        now = datetime.now(timezone.utc)
        async with self.sessions() as session:
            async with session.begin():
                # A worker may die on its final permitted attempt. Expire such
                # jobs as failed rather than leaving them stuck in "running".
                await session.execute(text("""
                    UPDATE crawl_jobs
                    SET status = 'failed',
                        locked_by = NULL,
                        locked_until = NULL,
                        last_error = COALESCE(last_error, 'Worker lease expired after final attempt'),
                        updated_at = :now
                    WHERE status = 'running'
                      AND locked_until < :now
                      AND attempts >= max_attempts
                """), {"now": now})
                row = (await session.execute(statement, {
                    "now": now,
                    "worker_id": worker_id,
                    "lease_until": now + timedelta(seconds=lease_seconds),
                })).mappings().first()
                if row is None:
                    return None
                return ClaimedJob(
                    id=row["id"], url=row["url"],
                    attempts=row["attempts"], max_attempts=row["max_attempts"],
                )

    async def renew_lease(
        self, job_id: uuid.UUID, worker_id: str, lease_seconds: int = 60
    ) -> bool:
        """Extend a lease only while this owner still holds an unexpired lease."""
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        now = datetime.now(timezone.utc)
        async with self.sessions() as session:
            async with session.begin():
                result = await session.execute(
                    update(CrawlJob)
                    .where(
                        CrawlJob.id == job_id,
                        CrawlJob.status == "running",
                        CrawlJob.locked_by == worker_id,
                        CrawlJob.locked_until > now,
                    )
                    .values(
                        locked_until=now + timedelta(seconds=lease_seconds),
                        updated_at=now,
                    )
                )
                return result.rowcount == 1

    async def complete(self, job_id: uuid.UUID, worker_id: str, page_id: uuid.UUID) -> bool:
        async with self.sessions() as session:
            async with session.begin():
                job = await session.scalar(
                    select(CrawlJob).where(
                        CrawlJob.id == job_id,
                        CrawlJob.status == "running",
                        CrawlJob.locked_by == worker_id,
                        CrawlJob.locked_until > datetime.now(timezone.utc),
                    ).with_for_update()
                )
                if job is None:
                    return False
                job.status = "completed"
                job.result_page_id = page_id
                job.completed_at = datetime.now(timezone.utc)
                job.locked_by = None
                job.locked_until = None
                job.last_error = None
                return True

    async def fail(self, job_id: uuid.UUID, worker_id: str, error: str) -> bool:
        async with self.sessions() as session:
            async with session.begin():
                job = await session.scalar(
                    select(CrawlJob).where(
                        CrawlJob.id == job_id,
                        CrawlJob.status == "running",
                        CrawlJob.locked_by == worker_id,
                    ).with_for_update()
                )
                if job is None:
                    return False
                now = datetime.now(timezone.utc)
                job.last_error = error[:4000]
                job.locked_by = None
                job.locked_until = None
                if job.attempts >= job.max_attempts:
                    job.status = "failed"
                else:
                    job.status = "pending"
                    delay = min(300, 2 ** min(job.attempts, 8))
                    job.available_at = now + timedelta(seconds=delay)
                return True

    async def queue_counts(self) -> dict[str, int]:
        async with self.sessions() as session:
            rows = await session.execute(
                select(CrawlJob.status, func.count())
                .where(CrawlJob.status.in_(("pending", "running")))
                .group_by(CrawlJob.status)
            )
            counts = {"pending": 0, "running": 0}
            for status, count in rows:
                counts[status] = count
            return counts

    async def get_active_by_url(self, url: str) -> CrawlJob | None:
        async with self.sessions() as session:
            return await session.scalar(
                select(CrawlJob).where(
                    CrawlJob.url == url,
                    CrawlJob.status.in_(("pending", "running")),
                ).limit(1)
            )

    async def get(self, job_id: uuid.UUID) -> CrawlJob | None:
        async with self.sessions() as session:
            return await session.get(CrawlJob, job_id)
