"""PostgreSQL full-text search over the latest page versions."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import Float, Integer, String, bindparam, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.models import Page, PageVersion


@dataclass(frozen=True)
class SearchHit:
    page_id: uuid.UUID
    url: str
    title: str | None
    snippet: str
    score: float
    version_number: int


def build_search_statement(query: str, limit: int = 10, offset: int = 0):
    """Build a parameterized PostgreSQL full-text query.

    The tsvector column is added by Alembic migration 0002. A literal column
    expression keeps ORM metadata portable for SQLite-based unit tests.
    """
    if not query or not query.strip():
        raise ValueError("query must not be empty")
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    if offset < 0:
        raise ValueError("offset must be non-negative")

    vector = literal_column("page_versions.search_vector")
    tsquery = bindparam("search_query", type_=String())
    parsed_query = __import__("sqlalchemy").func.websearch_to_tsquery("english", tsquery)
    score = __import__("sqlalchemy").func.ts_rank_cd(vector, parsed_query, 32).label("score")
    snippet = __import__("sqlalchemy").func.ts_headline(
        "english", PageVersion.extracted_text, parsed_query,
        "MaxWords=30, MinWords=10, ShortWord=2, HighlightAll=FALSE"
    ).label("snippet")

    return (
        select(
            Page.id.label("page_id"),
            Page.normalized_url.label("url"),
            Page.title.label("title"),
            snippet,
            score,
            PageVersion.version_number.label("version_number"),
        )
        .join(PageVersion, PageVersion.page_id == Page.id)
        .where(
            PageVersion.content_hash == Page.current_content_hash,
            vector.op("@@")(parsed_query),
        )
        .order_by(score.desc(), Page.last_crawled_at.desc())
        .limit(bindparam("result_limit", value=limit, type_=Integer()))
        .offset(bindparam("result_offset", value=offset, type_=Integer()))
        .params(search_query=query)
    )


class FullTextSearchRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def search(self, query: str, limit: int = 10, offset: int = 0) -> list[SearchHit]:
        statement = build_search_statement(query, limit, offset)
        async with self._sessions() as session:
            rows = (await session.execute(statement)).all()
        return [
            SearchHit(
                page_id=row.page_id,
                url=row.url,
                title=row.title,
                snippet=row.snippet,
                score=float(row.score),
                version_number=row.version_number,
            )
            for row in rows
        ]
