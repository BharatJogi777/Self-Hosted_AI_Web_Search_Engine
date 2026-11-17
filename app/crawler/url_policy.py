"""URL validation and normalization for a scoped web crawler.

This module performs string-level checks only. It does not resolve DNS or make
network requests; the HTTP fetcher must enforce destination-IP safety too.
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


class URLRejected(ValueError):
    """Raised when a URL violates crawler scope or safety policy."""


@dataclass(frozen=True, slots=True)
class URLPolicy:
    """Allow HTTP(S) URLs whose host is an explicitly allowed domain."""

    allowed_domains: frozenset[str] | set[str]
    allowed_ports: frozenset[int] = frozenset({80, 443})

    def __post_init__(self) -> None:
        normalized = frozenset(
            self._normalize_domain(domain) for domain in self.allowed_domains
        )
        if not normalized:
            raise ValueError("At least one allowed domain must be configured")
        object.__setattr__(self, "allowed_domains", normalized)

    @staticmethod
    def _normalize_domain(domain: str) -> str:
        value = domain.strip().rstrip(".").lower()
        if not value:
            raise ValueError("Allowed domain cannot be empty")
        try:
            return value.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ValueError(f"Invalid allowed domain: {domain!r}") from exc

    def normalize(self, raw_url: str) -> str:
        """Validate scope and return a normalized URL without its fragment."""
        if not isinstance(raw_url, str) or not raw_url.strip():
            raise URLRejected("URL must be a non-empty string")

        raw_url = raw_url.strip()
        try:
            parts = urlsplit(raw_url)
        except ValueError as exc:
            raise URLRejected("Malformed URL") from exc

        scheme = parts.scheme.lower()
        if scheme not in {"http", "https"}:
            raise URLRejected("Only http and https URLs are supported")
        if parts.username is not None or parts.password is not None:
            raise URLRejected("URLs containing credentials are not allowed")
        if not parts.hostname:
            raise URLRejected("URL must contain a hostname")

        host = parts.hostname.rstrip(".").lower()
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise URLRejected("Invalid hostname") from exc

        # Reject IP literals here. The fetcher will also validate DNS results
        # for hostnames to protect against private-address resolution/rebinding.
        try:
            ipaddress.ip_address(host.strip("[]"))
        except ValueError:
            pass
        else:
            raise URLRejected("IP-literal hosts are not allowed")

        if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
            raise URLRejected("Localhost destinations are not allowed")

        if not any(
            host == allowed or host.endswith("." + allowed)
            for allowed in self.allowed_domains
        ):
            raise URLRejected(f"Host {host!r} is outside the configured crawl scope")

        try:
            port = parts.port
        except ValueError as exc:
            raise URLRejected("Invalid port") from exc

        if port is not None and port not in self.allowed_ports:
            raise URLRejected(f"Port {port} is not allowed")

        # urlsplit().hostname removes brackets from IPv6, but IP literals have
        # already been rejected. Rebuild netloc without credentials.
        default_port = 80 if scheme == "http" else 443
        netloc = host if port is None or port == default_port else f"{host}:{port}"
        path = parts.path or "/"

        return urlunsplit((scheme, netloc, path, parts.query, ""))
