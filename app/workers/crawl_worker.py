from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
import uuid
from contextlib import suppress
from time import monotonic

from prometheus_client import start_http_server
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.crawler.fetcher import SafeHTTPFetcher
from app.crawler.url_policy import URLPolicy
from app.database.queue import CrawlJobRepository
from app.database.repository import PageRepository
from app.services.ingestion import IngestionService
from app.workers.logging_config import JsonLogFormatter
from app.workers.metrics import (
    ACTIVE_WORKERS,
    JOBS_CLAIMED,
    JOBS_COMPLETED,
    JOBS_FAILED,
    JOB_DURATION,
    LEASE_LOST,
    PENDING_JOBS,
    RUNNING_JOBS,
)

logger = logging.getLogger("search.crawl_worker")


async def _heartbeat(
    jobs: CrawlJobRepository,
    job_id: uuid.UUID,
    owner_token: str,
    lease_seconds: int,
    lost_lease: asyncio.Event,
) -> None:
    interval = max(1, lease_seconds // 3)
    while True:
        await asyncio.sleep(interval)
        try:
            renewed = await jobs.renew_lease(job_id, owner_token, lease_seconds)
        except Exception:
            logger.exception(
                "Lease heartbeat failed",
                extra={"event": "heartbeat_error", "job_id": str(job_id)},
            )
            lost_lease.set()
            return
        if not renewed:
            lost_lease.set()
            logger.warning(
                "Job lease could not be renewed",
                extra={"event": "lease_lost", "job_id": str(job_id)},
            )
            return


async def _worker_slot(
    slot_number: int,
    worker_id: str,
    jobs: CrawlJobRepository,
    ingestion: IngestionService,
    shutdown: asyncio.Event,
    lease_seconds: int,
    poll_seconds: float,
    domain_locks: dict[str, asyncio.Lock],
) -> None:
    while not shutdown.is_set():
        try:
            counts = await jobs.queue_counts()
            PENDING_JOBS.set(counts["pending"])
            RUNNING_JOBS.set(counts["running"])
        except Exception:
            logger.exception("Unable to refresh queue metrics", extra={"event": "metrics_error"})
        owner_token = f"{worker_id}:{slot_number}:{uuid.uuid4().hex}"
        try:
            job = await jobs.claim(owner_token, lease_seconds=lease_seconds)
        except Exception:
            logger.exception("Unable to claim crawl job", extra={"event": "claim_error"})
            await asyncio.sleep(poll_seconds)
            continue

        if job is None:
            try:
                await asyncio.wait_for(shutdown.wait(), timeout=poll_seconds)
            except asyncio.TimeoutError:
                pass
            continue

        JOBS_CLAIMED.inc()
        ACTIVE_WORKERS.inc()
        started = monotonic()
        lost_lease = asyncio.Event()
        heartbeat_task = asyncio.create_task(
            _heartbeat(jobs, job.id, owner_token, lease_seconds, lost_lease)
        )
        logger.info(
            "Crawl job started",
            extra={
                "event": "job_started",
                "worker_id": worker_id,
                "job_id": str(job.id),
                "attempt": job.attempts,
            },
        )
        try:
            from urllib.parse import urlsplit
            domain = urlsplit(job.url).hostname or ""
            # Serialize same-domain work inside this process. The fetcher's
            # host rate limiter remains an additional request-level control.
            async with domain_locks.setdefault(domain, asyncio.Lock()):
                saved, _ = await ingestion.crawl_one(job.url)

            if lost_lease.is_set():
                LEASE_LOST.inc()
                logger.warning(
                    "Skipping completion because this worker lost the lease",
                    extra={"event": "completion_skipped", "job_id": str(job.id)},
                )
                continue

            completed = await jobs.complete(job.id, owner_token, saved.page_id)
            if completed:
                JOBS_COMPLETED.inc()
                logger.info(
                    "Crawl job completed",
                    extra={
                        "event": "job_completed",
                        "worker_id": worker_id,
                        "job_id": str(job.id),
                        "duration_seconds": round(monotonic() - started, 3),
                    },
                )
            else:
                LEASE_LOST.inc()
                logger.warning(
                    "Job lease was no longer owned at completion",
                    extra={"event": "completion_rejected", "job_id": str(job.id)},
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            JOBS_FAILED.inc()
            logger.exception(
                "Crawl job failed",
                extra={
                    "event": "job_failed",
                    "worker_id": worker_id,
                    "job_id": str(job.id),
                    "attempt": job.attempts,
                },
            )
            if not lost_lease.is_set():
                await jobs.fail(
                    job.id, owner_token, f"{type(exc).__name__}: {exc}"
                )
        finally:
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat_task
            JOB_DURATION.observe(monotonic() - started)
            ACTIVE_WORKERS.dec()


async def run_worker() -> None:
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://search:search@localhost:5432/search_engine",
    )
    domains = frozenset(
        item.strip() for item in os.getenv("ALLOWED_DOMAINS", "").split(",") if item.strip()
    )
    if not domains:
        raise RuntimeError("ALLOWED_DOMAINS must contain at least one permitted domain")

    concurrency = int(os.getenv("WORKER_CONCURRENCY", "2"))
    lease_seconds = int(os.getenv("WORKER_LEASE_SECONDS", "120"))
    poll_seconds = float(os.getenv("WORKER_POLL_SECONDS", "1"))
    metrics_port = int(os.getenv("WORKER_METRICS_PORT", "9100"))
    if concurrency < 1 or lease_seconds < 6 or poll_seconds <= 0:
        raise ValueError("Invalid worker concurrency, lease, or polling configuration")

    engine = create_async_engine(database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    policy = URLPolicy(allowed_domains=domains)
    fetcher = SafeHTTPFetcher(policy)
    pages = PageRepository(sessions)
    jobs = CrawlJobRepository(sessions)
    ingestion = IngestionService(policy, fetcher, pages)
    worker_id = os.getenv("WORKER_ID", f"{socket.gethostname()}-{uuid.uuid4()}")
    shutdown = asyncio.Event()
    domain_locks: dict[str, asyncio.Lock] = {}

    try:
        start_http_server(metrics_port)
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError):
                loop.add_signal_handler(sig, shutdown.set)

        logger.info(
            "Worker process started",
            extra={
                "event": "worker_started",
                "worker_id": worker_id,
                "concurrency": concurrency,
            },
        )
        slots = [
            asyncio.create_task(
                _worker_slot(
                    slot,
                    worker_id,
                    jobs,
                    ingestion,
                    shutdown,
                    lease_seconds,
                    poll_seconds,
                    domain_locks,
                )
            )
            for slot in range(concurrency)
        ]
        await shutdown.wait()
        logger.info(
            "Worker shutdown requested",
            extra={"event": "shutdown_requested", "worker_id": worker_id},
        )
        await asyncio.gather(*slots)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        handlers=[handler],
        force=True,
    )
    asyncio.run(run_worker())
