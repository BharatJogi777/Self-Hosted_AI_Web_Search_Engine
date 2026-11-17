from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from app.crawler.fetcher import SafeHTTPFetcher
from app.crawler.robots import RobotsPolicy
from app.crawler.url_policy import URLPolicy
from app.database.repository import PageRepository, SaveDocumentResult
from app.extraction.html_extractor import extract_html


class RobotsDeniedError(PermissionError):
    """Raised when robots.txt disallows the requested URL."""


class IngestionService:
    """Orchestrate robots check, safe fetch, extraction, and persistence."""

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
        normalized = self.policy.normalize(raw_url)
        parts = urlsplit(normalized)
        origin = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
        robots_url = self.policy.normalize(origin + "/robots.txt")

        # Fail closed if robots.txt cannot be retrieved or parsed. The fetcher
        # applies URL scope, public-IP DNS checks, timeouts, and response limits.
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
        return saved, fetched.final_url
