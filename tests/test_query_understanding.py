import pytest

from app.search.query_understanding import QueryProcessor, default_query_processor


def test_normalizes_whitespace_without_lowercasing_original():
    result = default_query_processor().process("  PostgreSQL   CONNECTION pool  ")

    assert result.original == "  PostgreSQL   CONNECTION pool  "
    assert result.normalized == "PostgreSQL CONNECTION pool"


def test_corrects_known_spelling_error():
    result = default_query_processor().process("postgres conection pooling")

    assert result.corrected == "postgres connection pooling"
    assert ("conection", "connection") in result.corrections


def test_unknown_technical_identifier_is_preserved():
    processor = QueryProcessor(vocabulary=["postgresql", "connection"])
    result = processor.process("pgvector HNSW 768")

    assert result.corrected == "pgvector HNSW 768"


def test_synonym_expansion_is_bounded_and_deduplicated():
    processor = QueryProcessor(
        vocabulary=["postgresql", "database"],
        synonyms={"postgresql": ["postgres", "database", "postgres"]},
        max_expansions=2,
    )
    result = processor.process("postgresql")

    assert result.expansions == ("postgres", "database")
    assert result.expanded == "postgresql postgres database"


def test_suggestions_are_bounded():
    suggestions = default_query_processor().suggest("conection", limit=3)

    assert "connection" in suggestions
    assert len(suggestions) <= 3


@pytest.mark.parametrize("query", ["", "   "])
def test_empty_query_is_rejected(query):
    with pytest.raises(ValueError):
        default_query_processor().process(query)


def test_invalid_suggestion_limit_is_rejected():
    with pytest.raises(ValueError):
        default_query_processor().suggest("postgre", limit=0)
