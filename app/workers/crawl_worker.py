from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.crawler.fetcher import FetchError, SafeHTTPFetcher
from app.crawler.url_policy import URLPolicy
from app.database.queue import CrawlJobRepository
from app.database.repository import PageRepository
from app.services.ingestion import IngestionService

logger = logging.getLogger("search.crawl_worker")


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

    engine = create_async_engine(database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    policy = URLPolicy(allowed_domains=domains)
    fetcher = SafeHTTPFetcher(policy)
    pages = PageRepository(sessions)
    jobs = CrawlJobRepository(sessions)
    ingestion = IngestionService(policy, fetcher, pages)
    worker_id = os.getenv("WORKER_ID", f"{socket.gethostname()}-{uuid.uuid4()}")

    try:
        while True:
            job = await jobs.claim(worker_id, lease_seconds=120)
            if job is None:
                await asyncio.sleep(1)
                continue
            try:
                saved, _ = await ingestion.crawl_one(job.url)
                completed = await jobs.complete(job.id, worker_id, saved.page_id)
                if not completed:
                    logger.warning("Job lease lost before completion: %s", job.id)
            except Exception as exc:
                logger.exception("Crawl job failed: %s", job.id)
                await jobs.fail(job.id, worker_id, f"{type(exc).__name__}: {exc}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    asyncio.run(run_worker())
