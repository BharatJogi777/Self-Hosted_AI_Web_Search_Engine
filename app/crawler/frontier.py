"""A bounded, in-memory breadth-first crawl frontier."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from app.crawler.url_policy import URLPolicy, URLRejected


@dataclass(frozen=True, slots=True)
class CrawlTarget:
    url: str
    depth: int
    parent_url: str | None


class CrawlFrontier:
    """Queue normalized, in-scope URLs while enforcing crawl bounds."""

    def __init__(
        self,
        policy: URLPolicy,
        *,
        max_pages: int = 1_000,
        max_depth: int = 3,
    ) -> None:
        if max_pages < 1:
            raise ValueError("max_pages must be at least 1")
        if max_depth < 0:
            raise ValueError("max_depth cannot be negative")

        self.policy = policy
        self.max_pages = max_pages
        self.max_depth = max_depth
        self._queue: deque[CrawlTarget] = deque()
        self._seen: set[str] = set()

    @property
    def scheduled_count(self) -> int:
        return len(self._seen)

    @property
    def pending_count(self) -> int:
        return len(self._queue)

    def add(
        self,
        url: str,
        *,
        depth: int,
        parent_url: str | None,
    ) -> bool:
        """Add a URL if valid, in scope, unseen, and within configured limits.

        Returns False for duplicates or exhausted limits. Invalid/out-of-scope
        URLs raise URLRejected so callers can record the rejection reason.
        """
        if depth < 0:
            raise ValueError("depth cannot be negative")
        normalized = self.policy.normalize(url)

        if normalized in self._seen:
            return False
        if depth > self.max_depth or len(self._seen) >= self.max_pages:
            return False

        normalized_parent = (
            self.policy.normalize(parent_url) if parent_url is not None else None
        )
        self._seen.add(normalized)
        self._queue.append(
            CrawlTarget(
                url=normalized,
                depth=depth,
                parent_url=normalized_parent,
            )
        )
        return True

    def pop(self) -> CrawlTarget | None:
        """Return the next target, or None when the frontier is empty."""
        return self._queue.popleft() if self._queue else None
