"""Bounded sitemap XML parsing; URL scope validation remains the caller's job."""
from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree


@dataclass(frozen=True, slots=True)
class SitemapEntry:
    location: str
    last_modified: str | None = None


def parse_sitemap(xml_body: bytes, *, max_entries: int = 10_000) -> list[SitemapEntry]:
    """Parse a sitemap urlset or sitemapindex with a strict entry limit.

    XML is parsed by the standard library; callers must also enforce a small
    HTTP response-size limit before passing bytes here. This function does not
    fetch nested sitemap files or authorize the returned URLs.
    """
    if max_entries < 1:
        raise ValueError("max_entries must be positive")
    try:
        root = ElementTree.fromstring(xml_body)
    except ElementTree.ParseError as exc:
        raise ValueError("Invalid sitemap XML") from exc

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
    return entries
