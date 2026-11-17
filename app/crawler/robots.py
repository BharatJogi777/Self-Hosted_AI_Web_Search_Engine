"""Robots.txt parsing and URL permission checks."""
from __future__ import annotations

from urllib.robotparser import RobotFileParser
from urllib.parse import urlsplit, urlunsplit


class RobotsPolicy:
    """Evaluate robots.txt rules for one origin and crawler user-agent.

    Fetching robots.txt is intentionally outside this class. The caller must
    retrieve it through the same safe HTTP layer used for page requests.
    """

    def __init__(
        self,
        *,
        robots_url: str,
        user_agent: str,
        robots_text: str,
    ) -> None:
        parts = urlsplit(robots_url)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("robots_url must be an absolute HTTP(S) URL")
        self.robots_url = robots_url
        self.origin = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
        self.user_agent = user_agent
        self._parser = RobotFileParser()
        self._parser.set_url(robots_url)
        self._parser.parse(robots_text.splitlines())

    def can_fetch(self, url: str) -> bool:
        """Return whether robots rules allow this user-agent to fetch the URL."""
        candidate = urlsplit(url)
        candidate_origin = urlunsplit(
            (candidate.scheme, candidate.netloc, "", "", "")
        )
        if candidate_origin != self.origin:
            return False
        return self._parser.can_fetch(self.user_agent, url)
