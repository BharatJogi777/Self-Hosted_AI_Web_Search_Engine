from dataclasses import dataclass
from uuid import uuid4

import pytest

from app.search.hybrid_search import reciprocal_rank_fusion


@dataclass
class Candidate:
    page_id: object
    version_id: object
    url: str
    title: str
    domain: str
    snippet: str = ""
    content: str = ""


def candidate(page_id, text_value):
    return Candidate(
        page_id=page_id,
        version_id=uuid4(),
        url=f"https://example.com/{page_id}",
        title=f"Page {page_id}",
        domain="example.com",
        snippet=text_value,
        content=text_value,
    )


def test_rrf_rewards_documents_ranked_by_both_retrievers():
    shared, lexical_only, semantic_only = uuid4(), uuid4(), uuid4()
    lexical = [candidate(shared, "lexical shared"), candidate(lexical_only, "lexical")]
    semantic = [candidate(shared, "semantic shared"), candidate(semantic_only, "semantic")]

    results = reciprocal_rank_fusion(lexical, semantic, limit=3)

    assert results[0].page_id == shared
    assert results[0].lexical_rank == 1
    assert results[0].semantic_rank == 1
    assert results[0].fusion_score > results[1].fusion_score
    assert results[0].snippet == "semantic shared"


def test_rrf_is_deterministic_and_respects_limit():
    ids = [uuid4() for _ in range(4)]
    lexical = [candidate(item, "lexical") for item in ids]
    semantic = [candidate(item, "semantic") for item in reversed(ids)]

    first = reciprocal_rank_fusion(lexical, semantic, limit=2)
    second = reciprocal_rank_fusion(lexical, semantic, limit=2)

    assert len(first) == 2
    assert [item.page_id for item in first] == [item.page_id for item in second]


@pytest.mark.parametrize("limit", [0, 101])
def test_rrf_rejects_invalid_limit(limit):
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([], [], limit=limit)


def test_rrf_rejects_invalid_constant():
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([], [], rrf_k=0)
