from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.search.hybrid_search import HybridSearchRepository, HybridSearchResult


_TOKEN_RE = re.compile(r"[\\w]+", re.UNICODE)


@dataclass(frozen=True)
class RankedSearchResult:
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


class Reranker(Protocol):
    """Contract for replacing the baseline with a learned reranker later."""

    def rerank(
        self, query: str, candidates: list[HybridSearchResult], *, limit: int
    ) -> list[RankedSearchResult]: ...


def _tokens(value: str) -> set[str]:
    return {token.casefold() for token in _TOKEN_RE.findall(value) if len(token) > 1}


def _coverage(query_terms: set[str], text: str) -> float:
    if not query_terms:
        return 0.0
    return len(query_terms & _tokens(text)) / len(query_terms)


class TermCoverageReranker:
    """Small, deterministic reranker; no model download or extra dependency.

    It combines normalized RRF position with query-term coverage in the title
    and snippet. It is a transparent baseline, not a learned relevance model.
    """

    def __init__(self, *, rrf_k: int = 60) -> None:
        if rrf_k < 1:
            raise ValueError("rrf_k must be positive")
        self._rrf_k = rrf_k

    def rerank(
        self, query: str, candidates: list[HybridSearchResult], *, limit: int = 10
    ) -> list[RankedSearchResult]:
        if not query.strip():
            raise ValueError("query must not be empty")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")

        query_terms = _tokens(query)
        normalized_query = " ".join(query.casefold().split())
        max_rrf = 2.0 / (self._rrf_k + 1)
        ranked: list[RankedSearchResult] = []

        for candidate in candidates:
            title_coverage = _coverage(query_terms, candidate.title)
            snippet_coverage = _coverage(query_terms, candidate.snippet)
            normalized_title = " ".join(candidate.title.casefold().split())
            exact_title_match = bool(normalized_query) and normalized_query in normalized_title
            base_score = min(1.0, candidate.fusion_score / max_rrf)

            # Keep retrieval evidence dominant; lexical title/body signals refine it.
            score = (
                0.55 * base_score
                + 0.25 * title_coverage
                + 0.15 * snippet_coverage
                + 0.05 * float(exact_title_match)
            )
            ranked.append(RankedSearchResult(
                page_id=candidate.page_id,
                version_id=candidate.version_id,
                url=candidate.url,
                title=candidate.title,
                domain=candidate.domain,
                snippet=candidate.snippet,
                fusion_score=candidate.fusion_score,
                lexical_rank=candidate.lexical_rank,
                semantic_rank=candidate.semantic_rank,
                ranking_score=score,
                title_coverage=title_coverage,
                snippet_coverage=snippet_coverage,
                exact_title_match=exact_title_match,
            ))

        ranked.sort(
            key=lambda item: (-item.ranking_score, -item.fusion_score, str(item.page_id))
        )
        return ranked[:limit]


class RerankedSearchRepository:
    """Two-stage pipeline: hybrid candidate retrieval followed by reranking."""

    def __init__(
        self,
        hybrid_repository: HybridSearchRepository,
        reranker: Reranker,
        *,
        candidate_limit: int = 50,
    ) -> None:
        if not 1 <= candidate_limit <= 100:
            raise ValueError("candidate_limit must be between 1 and 100")
        self._hybrid = hybrid_repository
        self._reranker = reranker
        self._candidate_limit = candidate_limit

    async def search(
        self, query: str, *, limit: int = 10, domain: str | None = None
    ) -> list[RankedSearchResult]:
        if not query.strip():
            raise ValueError("query must not be empty")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        candidates = await self._hybrid.search(
            query, limit=self._candidate_limit, domain=domain
        )
        return self._reranker.rerank(query, candidates, limit=limit)
