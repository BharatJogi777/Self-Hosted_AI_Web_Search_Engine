from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.models import Page, PageVersion
from app.extraction.html_extractor import ExtractedDocument


@dataclass(frozen=True)
class SaveDocumentResult:
    page_id: uuid.UUID
    version_id: uuid.UUID | None
    version_number: int | None
    page_created: bool
    content_changed: bool


class PageRepository:
    """Persistence boundary between the crawler and the database."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def save_extracted_document(
        self, document: ExtractedDocument, normalized_url: str
    ) -> SaveDocumentResult:
        """Upsert page metadata and append a version only when text changes.

        normalized_url must already have passed the crawler URL policy.
        """
        now = datetime.now(timezone.utc)
        domain = urlsplit(normalized_url).hostname or ""

        async with self._sessions() as session:
            async with session.begin():
                page = await session.scalar(
                    select(Page).where(Page.normalized_url == normalized_url)
                )
                page_created = page is None
                if page is None:
                    page = Page(
                        normalized_url=normalized_url,
                        source_url=document.source_url,
                        domain=domain,
                        current_content_hash=document.content_hash,
                        last_crawled_at=now,
                    )
                    session.add(page)
                    await session.flush()
                    next_version = 1
                    content_changed = True
                else:
                    content_changed = page.current_content_hash != document.content_hash
                    next_version = None
                    if content_changed:
                        latest = await session.scalar(
                            select(func.max(PageVersion.version_number)).where(
                                PageVersion.page_id == page.id
                            )
                        )
                        next_version = (latest or 0) + 1

                page.source_url = document.source_url
                page.canonical_url = document.canonical_url
                page.domain = domain
                page.title = document.title
                page.description = document.description
                page.language = document.language
                page.last_crawled_at = now

                version_id = None
                version_number = None
                if content_changed:
                    version = PageVersion(
                        page_id=page.id,
                        version_number=next_version,
                        content_hash=document.content_hash,
                        extracted_text=document.text,
                        extractor=document.extractor,
                        fetched_at=now,
                    )
                    session.add(version)
                    page.current_content_hash = document.content_hash
                    await session.flush()
                    version_id = version.id
                    version_number = version.version_number

                result = SaveDocumentResult(
                    page_id=page.id,
                    version_id=version_id,
                    version_number=version_number,
                    page_created=page_created,
                    content_changed=content_changed,
                )
            return result

    async def get_page(self, normalized_url: str) -> Page | None:
        async with self._sessions() as session:
            return await session.scalar(select(Page).where(Page.normalized_url == normalized_url))

    async def list_versions(self, page_id: uuid.UUID) -> list[PageVersion]:
        async with self._sessions() as session:
            result = await session.scalars(
                select(PageVersion).where(PageVersion.page_id == page_id)
                .order_by(PageVersion.version_number)
            )
            return list(result.all())
