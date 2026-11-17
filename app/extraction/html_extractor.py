"""Extract searchable page content and metadata from HTML."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import trafilatura
from bs4 import BeautifulSoup


_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    source_url: str
    canonical_url: str | None
    title: str | None
    description: str | None
    language: str | None
    text: str
    content_hash: str
    extractor: str


def normalize_text(value: str) -> str:
    """Normalize whitespace without changing the words or punctuation."""
    return _WHITESPACE_RE.sub(" ", value).strip()


def _safe_metadata_url(candidate: str | None, base_url: str) -> str | None:
    """Resolve an HTTP(S) metadata URL; do not treat it as crawl authorization."""
    if not candidate:
        return None
    absolute = urljoin(base_url, candidate.strip())
    parts = urlsplit(absolute)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return None
    if parts.username is not None or parts.password is not None:
        return None
    return absolute


def extract_html(html: str | bytes, source_url: str) -> ExtractedDocument:
    """Extract main readable text and metadata from one HTML document.

    Trafilatura is the primary main-content extractor. BeautifulSoup supplies
    metadata and a conservative text fallback when Trafilatura returns no text.
    """
    if not source_url or not source_url.startswith(("http://", "https://")):
        raise ValueError("source_url must be an absolute HTTP(S) URL")

    if isinstance(html, bytes):
        html_text = html.decode("utf-8", errors="replace")
    else:
        html_text = html

    if not html_text.strip():
        raise ValueError("HTML content is empty")

    soup = BeautifulSoup(html_text, "lxml")

    # Remove elements that should not contribute to readable page text.
    for element in soup(
        ["script", "style", "noscript", "template", "svg", "canvas", "iframe"]
    ):
        element.decompose()

    for element in soup.find_all(
        ["nav", "footer", "header", "aside", "form"]
    ):
        element.decompose()

    title = None
    if soup.title and soup.title.string:
        title = normalize_text(soup.title.get_text(" ", strip=True)) or None

    description_tag = soup.find(
        "meta",
        attrs={"name": re.compile(r"^description$", re.IGNORECASE)},
    )
    description = None
    if description_tag and description_tag.get("content"):
        description = normalize_text(str(description_tag["content"])) or None

    canonical_tag = soup.find(
        "link",
        rel=lambda value: value and "canonical" in [
            token.lower() for token in (
                value if isinstance(value, list) else str(value).split()
            )
        ],
    )
    canonical_url = None
    if canonical_tag:
        canonical_url = _safe_metadata_url(
            canonical_tag.get("href"), source_url
        )

    html_tag = soup.find("html")
    language = None
    if html_tag and html_tag.get("lang"):
        language = normalize_text(str(html_tag["lang"])).lower() or None

    # Use the original HTML for Trafilatura because it has its own extraction
    # heuristics. Metadata parsing above uses the cleaned BeautifulSoup tree.
    extracted = trafilatura.extract(
        html_text,
        include_comments=False,
        include_tables=True,
        include_links=False,
        favor_precision=True,
        output_format="txt",
    )

    extractor = "trafilatura"
    main_text = normalize_text(extracted or "")

    if not main_text:
        extractor = "beautifulsoup_fallback"
        main_text = normalize_text(soup.get_text(" ", strip=True))

    if not main_text:
        raise ValueError("No readable text could be extracted from HTML")

    content_hash = hashlib.sha256(main_text.encode("utf-8")).hexdigest()

    return ExtractedDocument(
        source_url=source_url,
        canonical_url=canonical_url,
        title=title,
        description=description,
        language=language,
        text=main_text,
        content_hash=content_hash,
        extractor=extractor,
    )
