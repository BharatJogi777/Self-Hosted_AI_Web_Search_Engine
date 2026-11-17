from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


class CrawlRequest(BaseModel):
    url: HttpUrl


class CrawlResponse(BaseModel):
    page_id: UUID
    version_id: UUID | None
    version_number: int | None
    page_created: bool
    content_changed: bool
    final_url: str


class CrawlJobRequest(BaseModel):
    url: HttpUrl
    max_attempts: int = Field(default=5, ge=1, le=10)


class CrawlJobAccepted(BaseModel):
    job_id: UUID
    status: str


class CrawlJobStatus(BaseModel):
    job_id: UUID
    url: str
    status: str
    attempts: int
    max_attempts: int
    last_error: str | None
    result_page_id: UUID | None
    created_at: datetime
    completed_at: datetime | None


class SearchItem(BaseModel):
    page_id: UUID
    version_id: UUID
    url: str
    title: str
    domain: str
    snippet: str
    rank: float


class SearchResponse(BaseModel):
    query: str
    limit: int
    offset: int
    results: list[SearchItem]


class DocumentSummary(BaseModel):
    id: UUID
    url: str
    title: str | None
    domain: str
    current_content_hash: str
    last_crawled_at: datetime


class DocumentDetail(DocumentSummary):
    description: str | None
    language: str | None


class HealthResponse(BaseModel):
    status: str = Field(default="ok")
