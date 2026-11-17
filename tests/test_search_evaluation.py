import pytest

from app.search.evaluation import evaluate_query, evaluate_run


def test_perfect_ranking_has_perfect_metrics():
    result = evaluate_query(
        "q1",
        ["a", "b", "c"],
        {"a": 3, "b": 2, "c": 1},
        k=3,
    )

    assert result.precision_at_k == 1.0
    assert result.recall_at_k == 1.0
    assert result.reciprocal_rank_at_k == 1.0
    assert result.average_precision_at_k == 1.0
    assert result.ndcg_at_k == 1.0


def test_relevant_document_at_second_position():
    result = evaluate_query("q1", ["noise", "relevant"], {"relevant": 2}, k=2)

    assert result.precision_at_k == 0.5
    assert result.recall_at_k == 1.0
    assert result.reciprocal_rank_at_k == 0.5
    assert result.average_precision_at_k == 0.5
    assert 0.0 < result.ndcg_at_k < 1.0


def test_duplicate_results_are_counted_only_once():
    result = evaluate_query("q1", ["a", "a", "b"], {"a": 1, "b": 1}, k=3)

    assert result.recall_at_k == 1.0
    assert result.precision_at_k == pytest.approx(2 / 3)


def test_no_relevant_documents_returns_zero_metrics():
    result = evaluate_query("q1", ["a", "b"], {"a": 0}, k=2)

    assert result.recall_at_k == 0.0
    assert result.reciprocal_rank_at_k == 0.0
    assert result.ndcg_at_k == 0.0


def test_macro_averages_across_queries():
    queries = [
        {"query_id": "q1", "relevance": {"a": 1}},
        {"query_id": "q2", "relevance": {"b": 1}},
    ]
    per_query, aggregate = evaluate_run(
        queries,
        {"q1": ["a"], "q2": ["noise", "b"]},
        k=2,
    )

    assert len(per_query) == 2
    assert aggregate.query_count == 2
    assert aggregate.precision_at_k == pytest.approx(0.5)
    assert aggregate.mrr_at_k == pytest.approx(0.75)


@pytest.mark.parametrize("k", [0, -1])
def test_k_must_be_positive(k):
    with pytest.raises(ValueError):
        evaluate_query("q1", [], {}, k=k)


def test_negative_relevance_grade_is_rejected():
    with pytest.raises(ValueError):
        evaluate_query("q1", [], {"a": -1}, k=5)


def test_empty_query_set_is_rejected():
    with pytest.raises(ValueError):
        evaluate_run([], {}, k=5)
