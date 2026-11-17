from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.search.ollama_embeddings import OllamaEmbeddingClient
from app.search.postgres_search import PostgresSearchRepository
from app.search.semantic_search import SemanticSearchRepository


@dataclass(frozen=True)
class HybridSearchResult:
    page_id: UUID
    version_id: UUID
    url: str
    title: str
    domain: str
    snippet: str
    fusion_score: float
    lexical_rank: int | None
    semantic_rank: int | None


def reciprocal_rank_fusion(
    lexical_results: list,
    semantic_results: list,
    *,
    limit: int = 10,
    rrf_k: int = 60,
) -> list[HybridSearchResult]:
    """Fuse two ranked lists at page level using Reciprocal Rank Fusion.

    RRF uses rank positions rather than trying to compare raw PostgreSQL FTS
    scores with cosine similarities, which are on different scales.
    """
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    if rrf_k < 1:
        raise ValueError("rrf_k must be positive")

    combined: dict[UUID, dict] = {}

    for rank, item in enumerate(lexical_results, start=1):
        entry = combined.setdefault(item.page_id, {"lexical": None, "semantic": None, "score": 0.0, "item": item})
        if entry["lexical"] is None:
            entry["lexical"] = rank
            entry["score"] += 1.0 / (rrf_k + rank)
        entry["item"] = item

    for rank, item in enumerate(semantic_results, start=1):
        entry = combined.setdefault(item.page_id, {"lexical": None, "semantic": None, "score": 0.0, "item": item})
        if entry["semantic"] is None:
            entry["semantic"] = rank
            entry["score"] += 1.0 / (rrf_k + rank)
        # Prefer the semantic passage as a useful snippet when available.
        entry["item"] = item

    ranked = sorted(
        combined.items(),
        key=lambda pair: (-pair[1]["score"], str(pair[0])),
    )
    output = []
    for page_id, entry in ranked[:limit]:
        item = entry["item"]
        snippet = getattr(item, "content", None) or getattr(item, "snippet", "")
        output.append(HybridSearchResult(
            page_id=page_id,
            version_id=item.version_id,
            url=item.url,
            title=item.title,
            domain=item.domain,
            snippet=snippet,
            fusion_score=entry["score"],
            lexical_rank=entry["lexical"],
            semantic_rank=entry["semantic"],
        ))
    return output


class HybridSearchRepository:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        embeddings: OllamaEmbeddingClient,
        *,
        rrf_k: int = 60,
        candidate_limit: int = 50,
    ) -> None:
        self._lexical = PostgresSearchRepository(sessions)
        self._semantic = SemanticSearchRepository(sessions, embeddings)
        self._rrf_k = rrf_k
        self._candidate_limit = candidate_limit

    async def search(
        self, query: str, *, limit: int = 10, domain: str | None = None
    ) -> list[HybridSearchResult]:
        if not query.strip():
            raise ValueError("query must not be empty")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")

        lexical, semantic = await asyncio.gather(
            self._lexical.search(
                query, limit=self._candidate_limit, offset=0, domain=domain
            ),
            self._semantic.search(
                query, limit=self._candidate_limit, domain=domain
            ),
        )
        return reciprocal_rank_fusion(
            lexical, semantic, limit=limit, rrf_k=self._rrf_k
        )
