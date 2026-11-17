from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@dataclass(frozen=True)
class SearchResult:
    page_id: UUID
    version_id: UUID
    url: str
    title: str
    domain: str
    snippet: str
    rank: float


def build_search_statement():
    """Return parameterized PostgreSQL full-text search SQL."""
    return text("""
        WITH user_query AS (
            SELECT websearch_to_tsquery('english', :query) AS tsq
        )
        SELECT
            p.id AS page_id,
            pv.id AS version_id,
            p.normalized_url AS url,
            COALESCE(NULLIF(pv.title_snapshot, ''), p.title, p.normalized_url) AS title,
            p.domain AS domain,
            ts_headline(
                'english',
                pv.extracted_text,
                user_query.tsq,
                'StartSel=<mark>,StopSel=</mark>,MaxWords=32,MinWords=12'
            ) AS snippet,
            ts_rank_cd(pv.search_vector, user_query.tsq, 32) AS rank
        FROM page_versions AS pv
        JOIN pages AS p ON p.id = pv.page_id
        CROSS JOIN user_query
        WHERE pv.search_vector @@ user_query.tsq
          AND pv.content_hash = p.current_content_hash
          AND (:domain IS NULL OR p.domain = :domain)
        ORDER BY rank DESC, pv.fetched_at DESC
        LIMIT :limit OFFSET :offset
    """)


class PostgresSearchRepository:
    """Search the current stored version of each page using PostgreSQL FTS."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        offset: int = 0,
        domain: str | None = None,
    ) -> list[SearchResult]:
        cleaned = query.strip()
        if not cleaned:
            raise ValueError("query must not be empty")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if offset < 0:
            raise ValueError("offset must be zero or greater")

        async with self._sessions() as session:
            rows = (await session.execute(
                build_search_statement(),
                {"query": cleaned, "domain": domain, "limit": limit, "offset": offset},
            )).mappings().all()
        return [
            SearchResult(
                page_id=row["page_id"],
                version_id=row["version_id"],
                url=row["url"],
                title=row["title"],
                domain=row["domain"],
                snippet=row["snippet"],
                rank=float(row["rank"]),
            )
            for row in rows
        ]
