import pytest

from app.extraction.html_extractor import extract_html, normalize_text


HTML = """
<!doctype html>
<html lang="en">
<head>
  <title>  Building   Search Engines </title>
  <meta name="description" content="A practical guide to search.">
  <link rel="canonical" href="/guides/search">
  <script>const secret = "not article content";</script>
  <style>.banner { display: none; }</style>
</head>
<body>
  <header>Site header and navigation</header>
  <nav><a href="/home">Home</a></nav>
  <main>
    <article>
      <h1>Building a search engine</h1>
      <p>A crawler discovers pages and an index makes them searchable.</p>
      <p>Search retrieves and ranks relevant documents.</p>
    </article>
  </main>
  <aside>Related advertisements</aside>
  <footer>Copyright footer</footer>
</body>
</html>
"""


def test_normalize_text_collapses_whitespace() -> None:
    assert normalize_text("  one\n  two\t three  ") == "one two three"


def test_extracts_main_text_and_metadata() -> None:
    document = extract_html(HTML, "https://docs.example.com/start")

    assert document.source_url == "https://docs.example.com/start"
    assert document.canonical_url == "https://docs.example.com/guides/search"
    assert document.title == "Building Search Engines"
    assert document.description == "A practical guide to search."
    assert document.language == "en"
    assert "crawler discovers pages" in document.text
    assert "Search retrieves and ranks" in document.text
    assert "Site header" not in document.text
    assert "Related advertisements" not in document.text
    assert "Copyright footer" not in document.text
    assert "not article content" not in document.text
    assert len(document.content_hash) == 64


def test_hash_is_stable_for_same_extracted_text() -> None:
    first = extract_html(HTML, "https://docs.example.com/a")
    second = extract_html(HTML, "https://docs.example.com/b")
    assert first.content_hash == second.content_hash


def test_source_url_must_be_absolute_http_url() -> None:
    with pytest.raises(ValueError, match="absolute HTTP"):
        extract_html(HTML, "javascript:alert(1)")


def test_empty_html_is_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        extract_html("   ", "https://docs.example.com/")


def test_untrusted_canonical_scheme_is_ignored() -> None:
    html = """
    <html><head>
      <link rel="canonical" href="javascript:alert(1)">
    </head><body><main><p>Readable article text.</p></main></body></html>
    """
    document = extract_html(html, "https://docs.example.com/")
    assert document.canonical_url is None
