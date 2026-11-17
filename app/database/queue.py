from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.jobs import CrawlJob
from app.database.runs import CrawlRun


@dataclass(frozen=True)
class ClaimedJob:
    id: uuid.UUID
    url: str
    attempts: int
    max_attempts: int
    run_id: uuid.UUID | None = None
    depth: int = 0


class CrawlJobRepository:
    """PostgreSQL-backed queue using leases and SKIP LOCKED claims."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def create_run(
        self, seed_url: str, *, max_pages: int = 100, max_depth: int = 2,
        max_attempts: int = 5,
    ) -> tuple[CrawlRun, CrawlJob]:
        """Create a bounded run and reserve its seed URL in one transaction."""
        if max_pages < 1 or max_depth < 0:
            raise ValueError("max_pages must be positive and max_depth cannot be negative")
        now = datetime.now(timezone.utc)
        async with self.sessions() as session:
            async with session.begin():
                run = CrawlRun(
                    seed_url=seed_url, status="running", max_pages=max_pages,
                    max_depth=max_depth, discovered_count=1,
                )
                session.add(run)
                await session.flush()
                job = CrawlJob(
                    url=seed_url, run_id=run.id, depth=0, parent_url=None,
                    status="pending", attempts=0, max_attempts=max_attempts,
                    available_at=now,
                )
                session.add(job)
                await session.flush()
                return run, job

    async def enqueue_run_url(
        self, run_id: uuid.UUID, url: str, *, depth: int, parent_url: str,
        max_attempts: int = 5,
    ) -> bool:
        """Atomically reserve one run page slot and insert a unique run URL."""
        from sqlalchemy.exc import IntegrityError
        now = datetime.now(timezone.utc)
        try:
            async with self.sessions() as session:
                async with session.begin():
                    run = await session.scalar(
                        select(CrawlRun).where(CrawlRun.id == run_id).with_for_update()
                    )
                    if run is None or run.status != "running" or depth > run.max_depth:
                        return False
                    if run.discovered_count >= run.max_pages:
                        return False
                    run.discovered_count += 1
                    session.add(CrawlJob(
                        url=url, run_id=run_id, depth=depth, parent_url=parent_url,
                        status="pending", attempts=0, max_attempts=max_attempts,
                        available_at=now,
                    ))
                    await session.flush()
                    return True
        except IntegrityError:
            # Duplicate URL in this run or an already-active global URL.
            return False

    async def get_run(self, run_id: uuid.UUID) -> CrawlRun | None:
        async with self.sessions() as session:
            return await session.get(CrawlRun, run_id)

    async def run_job_counts(self, run_id: uuid.UUID) -> dict[str, int]:
        async with self.sessions() as session:
            rows = await session.execute(
                select(CrawlJob.status, func.count())
                .where(CrawlJob.run_id == run_id)
                .group_by(CrawlJob.status)
            )
            return {status: count for status, count in rows}

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
            RETURNING job.id, job.url, job.attempts, job.max_attempts, job.run_id, job.depth
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
                        CrawlJob.locked_until > datetime.now(timezone.utc),
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

    async def defer(self, job_id: uuid.UUID, worker_id: str, delay_seconds: float = 2.0) -> bool:
        """Return a claimed job to pending when shared domain capacity is busy."""
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
                        status="pending",
                        locked_by=None,
                        locked_until=None,
                        available_at=now + timedelta(seconds=max(0.5, delay_seconds)),
                        updated_at=now,
                    )
                )
                return result.rowcount == 1

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
