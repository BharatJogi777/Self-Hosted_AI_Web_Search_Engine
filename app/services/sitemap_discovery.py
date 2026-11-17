from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from app.crawler.fetcher import FetchError, SafeHTTPFetcher
from app.crawler.sitemap import parse_sitemap_document
from app.crawler.url_policy import URLPolicy, URLRejected


class SitemapDiscoveryService:
    """Discover a bounded set of same-origin page URLs from sitemap XML."""

    def __init__(
        self,
        policy: URLPolicy,
        fetcher: SafeHTTPFetcher,
        *,
        max_sitemaps: int = 5,
        max_urls: int = 500,
    ) -> None:
        if max_sitemaps < 1 or max_urls < 1:
            raise ValueError("Sitemap limits must be positive")
        self.policy = policy
        self.fetcher = fetcher
        self.max_sitemaps = max_sitemaps
        self.max_urls = max_urls

    async def discover(self, seed_url: str) -> list[str]:
        seed = self.policy.normalize(seed_url)
        parts = urlsplit(seed)
        origin = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
        pending = [self.policy.normalize(origin + "/sitemap.xml")]
        visited_sitemaps: set[str] = set()
        page_urls: set[str] = set()

        while pending and len(visited_sitemaps) < self.max_sitemaps and len(page_urls) < self.max_urls:
            sitemap_url = pending.pop(0)
            try:
                sitemap_url = self.policy.normalize(sitemap_url)
            except URLRejected:
                continue
            if urlsplit(sitemap_url).hostname != parts.hostname or sitemap_url in visited_sitemaps:
                continue
            visited_sitemaps.add(sitemap_url)
            try:
                response = await self.fetcher.fetch(sitemap_url)
                kind, entries = parse_sitemap_document(response.body, max_entries=self.max_urls)
            except (FetchError, ValueError):
                continue

            for entry in entries:
                try:
                    location = self.policy.normalize(entry.location)
                except URLRejected:
                    continue
                if urlsplit(location).hostname != parts.hostname:
                    continue
                if kind == "index":
                    if location not in visited_sitemaps and location not in pending:
                        pending.append(location)
                elif location != seed:
                    page_urls.add(location)
                    if len(page_urls) >= self.max_urls:
                        break

        return sorted(page_urls)[: self.max_urls]
