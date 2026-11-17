from uuid import UUID

import pytest

from app.search.hybrid_search import HybridSearchResult
from app.search.ranking import TermCoverageReranker


def candidate(
    page_id: int,
    *,
    title: str,
    snippet: str,
    fusion_score: float,
    lexical_rank: int | None = None,
    semantic_rank: int | None = None,
) -> HybridSearchResult:
    return HybridSearchResult(
        page_id=UUID(int=page_id),
        version_id=UUID(int=page_id + 100),
        url=f"https://example.com/{page_id}",
        title=title,
        domain="example.com",
        snippet=snippet,
        fusion_score=fusion_score,
        lexical_rank=lexical_rank,
        semantic_rank=semantic_rank,
    )


def test_title_and_snippet_relevance_can_improve_candidate_order():
    reranker = TermCoverageReranker()
    candidates = [
        candidate(1, title="General database guide", snippet="A broad overview", fusion_score=0.03),
        candidate(2, title="PostgreSQL connection pooling", snippet="Configure a connection pool safely", fusion_score=0.025),
    ]

    results = reranker.rerank("PostgreSQL connection pool", candidates, limit=2)

    assert results[0].page_id == UUID(int=2)
    assert results[0].title_coverage == 1.0
    assert results[0].snippet_coverage == 1.0


def test_exact_title_match_is_reported():
    result = TermCoverageReranker().rerank(
        "PostgreSQL indexing",
        [candidate(1, title="PostgreSQL indexing", snippet="GIN and GiST", fusion_score=0.02)],
        limit=1,
    )[0]

    assert result.exact_title_match is True
    assert result.ranking_score > 0


def test_order_is_deterministic_for_equal_signals():
    items = [
        candidate(2, title="same title", snippet="same text", fusion_score=0.02),
        candidate(1, title="same title", snippet="same text", fusion_score=0.02),
    ]

    results = TermCoverageReranker().rerank("same title", items, limit=2)

    assert [item.page_id for item in results] == [UUID(int=1), UUID(int=2)]


@pytest.mark.parametrize("query,limit", [("", 5), ("query", 0), ("query", 101)])
def test_invalid_query_or_limit_is_rejected(query, limit):
    with pytest.raises(ValueError):
        TermCoverageReranker().rerank(query, [], limit=limit)


def test_invalid_rrf_constant_is_rejected():
    with pytest.raises(ValueError):
        TermCoverageReranker(rrf_k=0)
