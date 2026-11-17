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


class CrawlRunRequest(BaseModel):
    url: HttpUrl
    max_pages: int = Field(default=100, ge=1, le=5000)
    max_depth: int = Field(default=2, ge=0, le=10)
    max_attempts: int = Field(default=5, ge=1, le=10)


class CrawlRunAccepted(BaseModel):
    run_id: UUID
    seed_job_id: UUID
    status: str
    max_pages: int
    max_depth: int


class CrawlRunStatus(BaseModel):
    run_id: UUID
    seed_url: str
    status: str
    max_pages: int
    max_depth: int
    discovered_count: int
    job_counts: dict[str, int]


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


class SemanticIndexResponse(BaseModel):
    page_id: UUID
    version_id: UUID
    chunk_count: int
    embedding_model: str


class SemanticSearchItem(BaseModel):
    page_id: UUID
    version_id: UUID
    chunk_id: UUID
    url: str
    title: str
    domain: str
    content: str
    distance: float
    score: float


class SemanticSearchResponse(BaseModel):
    query: str
    limit: int
    results: list[SemanticSearchItem]


class HybridSearchItem(BaseModel):
    page_id: UUID
    version_id: UUID
    url: str
    title: str
    domain: str
    snippet: str
    fusion_score: float
    lexical_rank: int | None
    semantic_rank: int | None


class HybridSearchResponse(BaseModel):
    query: str
    limit: int
    results: list[HybridSearchItem]


class RerankedSearchItem(BaseModel):
    page_id: UUID
    version_id: UUID
    url: str
    title: str
    domain: str
    snippet: str
    fusion_score: float
    lexical_rank: int | None
    semantic_rank: int | None
    ranking_score: float
    title_coverage: float
    snippet_coverage: float
    exact_title_match: bool


class RerankedSearchResponse(BaseModel):
    query: str
    limit: int
    normalized_query: str
    corrected_query: str
    expanded_query: str
    results: list[RerankedSearchItem]


class QuerySuggestionResponse(BaseModel):
    query: str
    suggestions: list[str]


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class AskSource(BaseModel):
    id: str
    url: str
    title: str


class AskResponse(BaseModel):
    question: str
    answer: str
    sources: list[AskSource]
    tool_calls: int
