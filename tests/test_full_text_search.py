import pytest
from sqlalchemy.dialects import postgresql

from app.search.full_text import build_search_statement


def test_search_statement_uses_tsvector_match_and_rank():
    statement = build_search_statement("distributed systems")
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "websearch_to_tsquery" in sql
    assert "ts_rank_cd" in sql
    assert "page_versions.search_vector" in sql
    assert "@@" in sql
    assert "page_versions.content_hash = pages.current_content_hash" in sql


def test_search_statement_is_parameterized():
    statement = build_search_statement("python' OR true --")
    compiled = statement.compile(dialect=postgresql.dialect())
    assert "python' OR true --" not in str(compiled)
    assert "search_query" in compiled.params


@pytest.mark.parametrize(
    "kwargs",
    [
        {"query": ""},
        {"query": "   "},
        {"query": "hello", "limit": 0},
        {"query": "hello", "limit": 101},
        {"query": "hello", "offset": -1},
    ],
)
def test_invalid_search_arguments_are_rejected(kwargs):
    with pytest.raises(ValueError):
        build_search_statement(**kwargs)
