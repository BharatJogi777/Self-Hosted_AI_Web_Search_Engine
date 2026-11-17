"""Bounded sitemap XML parsing; URL scope validation remains the caller's job."""
from __future__ import annotations

from dataclasses import dataclass
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException


@dataclass(frozen=True, slots=True)
class SitemapEntry:
    location: str
    last_modified: str | None = None


def parse_sitemap_document(
    xml_body: bytes, *, max_entries: int = 10_000
) -> tuple[str, list[SitemapEntry]]:
    """Return ('urlset'|'index', entries), enforcing an entry limit."""
    if max_entries < 1:
        raise ValueError("max_entries must be positive")
    try:
        root = ElementTree.fromstring(xml_body)
    except (ElementTree.ParseError, DefusedXmlException) as exc:
        raise ValueError("Invalid sitemap XML") from exc

    root_name = root.tag.rsplit("}", 1)[-1].lower()
    if root_name not in {"urlset", "sitemapindex"}:
        raise ValueError("Unsupported sitemap root element")
    kind = "index" if root_name == "sitemapindex" else "urlset"
    entries: list[SitemapEntry] = []
    for node in list(root):
        if len(entries) >= max_entries:
            break
        location = None
        last_modified = None
        for child in list(node):
            name = child.tag.rsplit("}", 1)[-1]
            if name == "loc" and child.text:
                location = child.text.strip()
            elif name == "lastmod" and child.text:
                last_modified = child.text.strip()
        if location:
            entries.append(SitemapEntry(location, last_modified))
    return kind, entries


def parse_sitemap(xml_body: bytes, *, max_entries: int = 10_000) -> list[SitemapEntry]:
    """Compatibility helper returning entries from either sitemap format."""
    return parse_sitemap_document(xml_body, max_entries=max_entries)[1]
