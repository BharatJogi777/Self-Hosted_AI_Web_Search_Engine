from __future__ import annotations

from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from app.crawler.fetcher import SafeHTTPFetcher
from app.crawler.robots import RobotsPolicy
from app.crawler.url_policy import URLPolicy
from app.database.repository import PageRepository, SaveDocumentResult
from app.extraction.html_extractor import extract_html


class RobotsDeniedError(PermissionError):
    """Raised when robots.txt disallows the requested URL."""


class IngestionService:
    """Orchestrate robots check, safe fetch, extraction, link discovery, and persistence."""

    def __init__(
        self,
        policy: URLPolicy,
        fetcher: SafeHTTPFetcher,
        repository: PageRepository,
    ) -> None:
        self.policy = policy
        self.fetcher = fetcher
        self.repository = repository

    async def crawl_one(self, raw_url: str) -> tuple[SaveDocumentResult, str]:
        saved, final_url, _ = await self.crawl_one_with_links(raw_url)
        return saved, final_url

    async def crawl_one_with_links(
        self, raw_url: str, *, max_links: int = 1000
    ) -> tuple[SaveDocumentResult, str, list[str]]:
        """Crawl one page and extract bounded same-host links from its response."""
        if max_links < 1:
            raise ValueError("max_links must be positive")
        normalized = self.policy.normalize(raw_url)
        parts = urlsplit(normalized)
        origin = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
        robots_url = self.policy.normalize(origin + "/robots.txt")

        # Fail closed when robots.txt cannot be retrieved. Persistent cache
        # integration and detailed HTTP status semantics are handled separately.
        robots_result = await self.fetcher.fetch(robots_url)
        robots_text = robots_result.body.decode("utf-8", errors="replace")
        robots = RobotsPolicy(
            robots_url=robots_url,
            user_agent=self.fetcher.user_agent,
            robots_text=robots_text,
        )
        if not robots.can_fetch(normalized):
            raise RobotsDeniedError("robots.txt disallows this URL")

        fetched = await self.fetcher.fetch(normalized)
        if fetched.content_type not in {"text/html", "application/xhtml+xml"}:
            raise ValueError("Only HTML pages can be ingested")

        document = extract_html(fetched.body, fetched.final_url)
        saved = await self.repository.save_extracted_document(
            document,
            normalized_url=self.policy.normalize(fetched.final_url),
        )

        final_parts = urlsplit(fetched.final_url)
        discovered: set[str] = set()
        soup = BeautifulSoup(fetched.body, "lxml")
        for anchor in soup.find_all("a", href=True):
            try:
                candidate = self.policy.normalize(urljoin(fetched.final_url, anchor["href"]))
            except (ValueError, TypeError):
                continue
            if urlsplit(candidate).hostname != final_parts.hostname:
                continue
            if candidate != self.policy.normalize(fetched.final_url):
                discovered.add(candidate)
            if len(discovered) >= max_links:
                break

        return saved, fetched.final_url, sorted(discovered)
