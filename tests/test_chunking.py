import pytest

from app.search.chunking import chunk_text


def test_empty_text_returns_no_chunks():
    assert chunk_text("  \n ") == []


def test_chunks_respect_maximum_and_have_stable_hashes():
    source = " ".join(f"word{i}" for i in range(600))
    first = chunk_text(source, max_chars=300, overlap=40)
    second = chunk_text(source, max_chars=300, overlap=40)

    assert len(first) > 1
    assert all(len(chunk.content) <= 300 for chunk in first)
    assert [item.content_hash for item in first] == [item.content_hash for item in second]
    assert [item.index for item in first] == list(range(len(first)))


@pytest.mark.parametrize(
    ("max_chars", "overlap"),
    [(99, 0), (100, 100), (100, -1)],
)
def test_invalid_chunk_configuration(max_chars, overlap):
    with pytest.raises(ValueError):
        chunk_text("hello world", max_chars=max_chars, overlap=overlap)
