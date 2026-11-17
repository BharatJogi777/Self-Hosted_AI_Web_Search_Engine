from dataclasses import dataclass

import pytest

from app.crawler.url_policy import URLPolicy
from app.services.sitemap_discovery import SitemapDiscoveryService


@dataclass
class FakeResponse:
    body: bytes


class FakeFetcher:
    user_agent = "test-bot"

    def __init__(self, responses):
        self.responses = responses
        self.requested = []

    async def fetch(self, url):
        self.requested.append(url)
        if url not in self.responses:
            from app.crawler.fetcher import FetchError
            raise FetchError("not found")
        return FakeResponse(self.responses[url])


@pytest.mark.asyncio
async def test_follows_sitemap_index_and_keeps_same_host_urls():
    root = b"""<sitemapindex>
      <sitemap><loc>https://example.com/part.xml</loc></sitemap>
    </sitemapindex>"""
    child = b"""<urlset>
      <url><loc>https://example.com/a</loc></url>
      <url><loc>https://outside.test/not-allowed</loc></url>
    </urlset>"""
    fetcher = FakeFetcher({
        "https://example.com/sitemap.xml": root,
        "https://example.com/part.xml": child,
    })
    service = SitemapDiscoveryService(
        URLPolicy(frozenset({"example.com"})), fetcher
    )

    found = await service.discover("https://example.com/")

    assert found == ["https://example.com/a"]
    assert fetcher.requested == [
        "https://example.com/sitemap.xml",
        "https://example.com/part.xml",
    ]


@pytest.mark.asyncio
async def test_sitemap_cycle_is_not_fetched_twice():
    root = b"""<sitemapindex>
      <sitemap><loc>https://example.com/sitemap.xml</loc></sitemap>
    </sitemapindex>"""
    fetcher = FakeFetcher({"https://example.com/sitemap.xml": root})
    service = SitemapDiscoveryService(
        URLPolicy(frozenset({"example.com"})), fetcher
    )

    assert await service.discover("https://example.com/") == []
    assert fetcher.requested == ["https://example.com/sitemap.xml"]
