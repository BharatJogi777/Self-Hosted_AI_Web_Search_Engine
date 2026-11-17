from __future__ import annotations

from dataclasses import asdict, dataclass
from math import log2
from typing import Mapping, Sequence


@dataclass(frozen=True)
class QueryMetrics:
    query_id: str
    precision_at_k: float
    recall_at_k: float
    reciprocal_rank_at_k: float
    average_precision_at_k: float
    ndcg_at_k: float


@dataclass(frozen=True)
class AggregateMetrics:
    query_count: int
    k: int
    precision_at_k: float
    recall_at_k: float
    mrr_at_k: float
    map_at_k: float
    ndcg_at_k: float


def _validate_k(k: int) -> None:
    if k < 1:
        raise ValueError("k must be at least 1")


def _unique_in_order(document_ids: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for document_id in document_ids:
        normalized = str(document_id)
        if normalized not in seen:
            seen.add(normalized)
            output.append(normalized)
    return output


def evaluate_query(
    query_id: str,
    ranked_document_ids: Sequence[str],
    relevance: Mapping[str, int],
    *,
    k: int = 10,
) -> QueryMetrics:
    """Evaluate one ranked list against graded relevance judgments.

    Relevance grade 0 means non-relevant; grades above 0 are relevant.
    Duplicate result IDs are ignored after their first occurrence.
    """
    _validate_k(k)
    if any(not isinstance(grade, int) or grade < 0 for grade in relevance.values()):
        raise ValueError("relevance grades must be non-negative integers")

    ranked = _unique_in_order(ranked_document_ids)[:k]
    relevant_ids = {str(doc_id) for doc_id, grade in relevance.items() if grade > 0}
    relevant_count = len(relevant_ids)

    relevant_hits = [
        index for index, doc_id in enumerate(ranked, start=1)
        if doc_id in relevant_ids
    ]
    precision = len(relevant_hits) / k
    recall = len(relevant_hits) / relevant_count if relevant_count else 0.0
    reciprocal_rank = 1.0 / relevant_hits[0] if relevant_hits else 0.0

    precision_sum = sum(
        hit_count / rank
        for rank, doc_id in enumerate(ranked, start=1)
        if doc_id in relevant_ids
        for hit_count in [sum(1 for prior in ranked[:rank] if prior in relevant_ids)]
    )
    ap_denominator = min(relevant_count, k)
    average_precision = precision_sum / ap_denominator if ap_denominator else 0.0

    def dcg(document_ids: Sequence[str]) -> float:
        return sum(
            (2 ** relevance.get(doc_id, 0) - 1) / log2(rank + 1)
            for rank, doc_id in enumerate(document_ids, start=1)
        )

    ideal_grades = sorted(relevance.values(), reverse=True)[:k]
    ideal_dcg = sum(
        (2 ** grade - 1) / log2(rank + 1)
        for rank, grade in enumerate(ideal_grades, start=1)
    )
    actual_dcg = dcg(ranked)
    ndcg = actual_dcg / ideal_dcg if ideal_dcg else 0.0

    return QueryMetrics(
        query_id=query_id,
        precision_at_k=precision,
        recall_at_k=recall,
        reciprocal_rank_at_k=reciprocal_rank,
        average_precision_at_k=average_precision,
        ndcg_at_k=ndcg,
    )


def evaluate_run(
    queries: Sequence[Mapping],
    results_by_query: Mapping[str, Sequence[str]],
    *,
    k: int = 10,
) -> tuple[list[QueryMetrics], AggregateMetrics]:
    """Evaluate a run and return per-query plus macro-averaged metrics."""
    _validate_k(k)
    if not queries:
        raise ValueError("at least one judged query is required")

    per_query = [
        evaluate_query(
            str(query["query_id"]),
            results_by_query.get(str(query["query_id"]), []),
            query["relevance"],
            k=k,
        )
        for query in queries
    ]
    count = len(per_query)

    def mean(field: str) -> float:
        return sum(getattr(item, field) for item in per_query) / count

    aggregate = AggregateMetrics(
        query_count=count,
        k=k,
        precision_at_k=mean("precision_at_k"),
        recall_at_k=mean("recall_at_k"),
        mrr_at_k=mean("reciprocal_rank_at_k"),
        map_at_k=mean("average_precision_at_k"),
        ndcg_at_k=mean("ndcg_at_k"),
    )
    return per_query, aggregate


def metrics_as_dict(metrics: QueryMetrics | AggregateMetrics) -> dict:
    """Convert a metrics dataclass to a JSON-serializable dictionary."""
    return asdict(metrics)
