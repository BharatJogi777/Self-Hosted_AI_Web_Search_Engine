from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, Integer, String, Text, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class CrawlDomain(Base):
    __tablename__ = "crawl_domains"

    domain: Mapped[str] = mapped_column(String(255), primary_key=True)
    next_allowed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(200), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    robots_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    robots_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    robots_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    robots_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class CrawlDomainRepository:
    """PostgreSQL-coordinated domain lease and robots cache."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def try_acquire(self, domain: str, owner: str, lease_seconds: int = 120) -> bool:
        now = datetime.now(timezone.utc)
        async with self.sessions() as session:
            async with session.begin():
                # PostgreSQL upsert creates the coordination row exactly once.
                statement = pg_insert(CrawlDomain).values(
                    domain=domain, next_allowed_at=now
                ).on_conflict_do_nothing(index_elements=[CrawlDomain.domain])
                await session.execute(statement)
                result = await session.execute(
                    update(CrawlDomain)
                    .where(
                        CrawlDomain.domain == domain,
                        CrawlDomain.next_allowed_at <= now,
                        (CrawlDomain.lease_until.is_(None) | (CrawlDomain.lease_until < now)),
                    )
                    .values(
                        lease_owner=owner,
                        lease_until=now + timedelta(seconds=lease_seconds),
                        updated_at=now,
                    )
                )
                return result.rowcount == 1

    async def release(self, domain: str, owner: str, minimum_interval_seconds: float = 1.0) -> bool:
        now = datetime.now(timezone.utc)
        async with self.sessions() as session:
            async with session.begin():
                result = await session.execute(
                    update(CrawlDomain)
                    .where(CrawlDomain.domain == domain, CrawlDomain.lease_owner == owner)
                    .values(
                        lease_owner=None,
                        lease_until=None,
                        next_allowed_at=now + timedelta(seconds=max(0.0, minimum_interval_seconds)),
                        updated_at=now,
                    )
                )
                return result.rowcount == 1

    async def renew(self, domain: str, owner: str, lease_seconds: int = 120) -> bool:
        now = datetime.now(timezone.utc)
        async with self.sessions() as session:
            async with session.begin():
                result = await session.execute(
                    update(CrawlDomain)
                    .where(
                        CrawlDomain.domain == domain,
                        CrawlDomain.lease_owner == owner,
                        CrawlDomain.lease_until > now,
                    )
                    .values(lease_until=now + timedelta(seconds=lease_seconds), updated_at=now)
                )
                return result.rowcount == 1

    async def get_robots_cache(self, domain: str) -> CrawlDomain | None:
        async with self.sessions() as session:
            return await session.scalar(select(CrawlDomain).where(CrawlDomain.domain == domain))

    async def save_robots_cache(
        self, domain: str, text: str, status: int, ttl_seconds: int = 86400
    ) -> None:
        now = datetime.now(timezone.utc)
        async with self.sessions() as session:
            async with session.begin():
                row = await session.get(CrawlDomain, domain)
                if row is None:
                    row = CrawlDomain(domain=domain, next_allowed_at=now)
                    session.add(row)
                row.robots_text = text
                row.robots_status = status
                row.robots_fetched_at = now
                row.robots_expires_at = now + timedelta(seconds=ttl_seconds)
