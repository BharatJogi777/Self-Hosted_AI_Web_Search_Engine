from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Page(Base):
    """Stable identity and latest metadata for a crawled URL."""
    __tablename__ = "pages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    normalized_url: Mapped[str] = mapped_column(String(2048), unique=True)
    source_url: Mapped[str] = mapped_column(String(2048))
    canonical_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    domain: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    current_content_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_crawled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    versions: Mapped[list["PageVersion"]] = relationship(
        back_populates="page", cascade="all, delete-orphan", order_by="PageVersion.version_number"
    )


class PageVersion(Base):
    """Immutable snapshot of extracted text for one page revision."""
    __tablename__ = "page_versions"
    __table_args__ = (
        UniqueConstraint("page_id", "version_number", name="uq_page_version_number"),
        UniqueConstraint("page_id", "content_hash", name="uq_page_version_content_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    page_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("pages.id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    title_snapshot: Mapped[str] = mapped_column(Text, default="")
    extracted_text: Mapped[str] = mapped_column(Text)
    extractor: Mapped[str] = mapped_column(String(100))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    page: Mapped[Page] = relationship(back_populates="versions")
