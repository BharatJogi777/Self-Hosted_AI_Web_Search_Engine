"""Bounded asynchronous HTTP fetching for the scoped crawler.

The custom resolver validates every resolved address before aiohttp connects.
Redirects are handled manually so every new URL is revalidated by URLPolicy.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlsplit

import aiohttp
from aiohttp.abc import AbstractResolver

from app.crawler.url_policy import URLPolicy, URLRejected


class FetchError(RuntimeError):
    """Base class for expected fetch failures."""


class UnsafeAddressError(FetchError):
    """Raised when DNS resolves to a non-public or invalid address."""


class ResponseTooLargeError(FetchError):
    """Raised when a response exceeds the configured byte limit."""


class UnsupportedContentTypeError(FetchError):
    """Raised when a response is not an allowed text document."""


@dataclass(frozen=True, slots=True)
class FetchResult:
    requested_url: str
    final_url: str
    status: int
    content_type: str
    body: bytes
    fetched_at: datetime
    elapsed_seconds: float


def is_public_ip(value: str) -> bool:
    """Return True only for globally routable unicast IP addresses."""
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address.is_global and not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


class PublicOnlyResolver(AbstractResolver):
    """Resolve hostnames but return only globally routable addresses.

    aiohttp uses these returned addresses for the connection while retaining
    the original hostname for the HTTP Host header and TLS certificate check.
    """

    async def resolve(
        self, host: str, port: int = 0, family: int = socket.AF_INET
    ) -> list[dict[str, Any]]:
        loop = asyncio.get_running_loop()
        try:
            records = await loop.getaddrinfo(
                host,
                port,
                family=family,
                type=socket.SOCK_STREAM,
            )
        except OSError as exc:
            raise FetchError(f"DNS resolution failed for {host}") from exc

        addresses: dict[str, dict[str, Any]] = {}
        for record in records:
            address = record[4][0]
            if not is_public_ip(address):
                raise UnsafeAddressError(
                    f"Host {host!r} resolved to a non-public address"
                )
            addresses[address] = {
                "hostname": host,
                "host": address,
                "port": port,
                "family": record[0],
                "proto": record[2],
                "flags": record[3],
            }

        if not addresses:
            raise FetchError(f"No usable DNS addresses for {host}")
        return list(addresses.values())

    async def close(self) -> None:
        return None


class HostRateLimiter:
    """Simple in-process minimum-interval limiter, keyed by hostname."""

    def __init__(self, min_interval_seconds: float = 1.0) -> None:
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds cannot be negative")
        self.min_interval_seconds = min_interval_seconds
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_request: dict[str, float] = {}

    async def wait(self, host: str) -> None:
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            previous = self._last_request.get(host)
            if previous is not None:
                delay = self.min_interval_seconds - (now - previous)
                if delay > 0:
                    await asyncio.sleep(delay)
            self._last_request[host] = time.monotonic()


def parse_retry_after(value: str | None) -> float | None:
    """Parse Retry-After as seconds or an HTTP date."""
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(value)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


async def read_limited_body(response: Any, max_bytes: int) -> bytes:
    """Read a streaming response while enforcing a decoded-byte limit."""
    if max_bytes < 1:
        raise ValueError("max_bytes must be at least 1")

    declared = response.headers.get("Content-Length")
    if declared:
        try:
            if int(declared) > max_bytes:
                raise ResponseTooLargeError("Response Content-Length exceeds limit")
        except ValueError:
            # Ignore malformed Content-Length; enforce the streaming limit.
            pass

    chunks: list[bytes] = []
    total = 0
    async for chunk in response.content.iter_chunked(64 * 1024):
        total += len(chunk)
        if total > max_bytes:
            raise ResponseTooLargeError("Response body exceeded configured limit")
        chunks.append(chunk)
    return b"".join(chunks)


class SafeHTTPFetcher:
    """Fetch HTML pages with scope, DNS, redirect, size, retry and rate limits."""

    RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
    ALLOWED_CONTENT_TYPES = {"text/html", "application/xhtml+xml", "text/plain", "application/xml", "text/xml"}

    def __init__(
        self,
        policy: URLPolicy,
        *,
        user_agent: str = "SelfHostedSearchBot/0.1 (+https://example.invalid/bot)",
        timeout_seconds: float = 15.0,
        max_response_bytes: int = 2_000_000,
        max_redirects: int = 5,
        max_retries: int = 2,
        min_host_interval_seconds: float = 1.0,
        max_retry_after_seconds: float = 10.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_response_bytes < 1:
            raise ValueError("max_response_bytes must be positive")
        if max_redirects < 0 or max_retries < 0:
            raise ValueError("redirect and retry limits cannot be negative")

        self.policy = policy
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.max_redirects = max_redirects
        self.max_retries = max_retries
        self.max_retry_after_seconds = max_retry_after_seconds
        self.rate_limiter = HostRateLimiter(min_host_interval_seconds)

    async def fetch(self, raw_url: str) -> FetchResult:
        requested_url = self.policy.normalize(raw_url)
        started = time.monotonic()
        current_url = requested_url
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        resolver = PublicOnlyResolver()
        connector = aiohttp.TCPConnector(
            resolver=resolver,
            use_dns_cache=False,
            limit=10,
            limit_per_host=2,
        )
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,text/plain,application/xml,text/xml;q=0.8",
        }

        async with aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers=headers,
            trust_env=False,
            auto_decompress=True,
        ) as session:
            for redirect_count in range(self.max_redirects + 1):
                current_url = self.policy.normalize(current_url)
                host = urlsplit(current_url).hostname
                assert host is not None
                await self.rate_limiter.wait(host)

                response = await self._request_with_retries(session, current_url)

                if response.status in {301, 302, 303, 307, 308}:
                    location = response.headers.get("Location")
                    response.release()
                    if not location:
                        raise FetchError("Redirect response did not include Location")
                    if redirect_count >= self.max_redirects:
                        raise FetchError("Maximum redirect count exceeded")
                    # urljoin handles relative redirects; policy.normalize
                    # validates scope and scheme on the next iteration.
                    current_url = urljoin(current_url, location)
                    current_url = self.policy.normalize(current_url)
                    continue

                if response.status < 200 or response.status >= 300:
                    status = response.status
                    response.release()
                    raise FetchError(f"HTTP request failed with status {status}")

                content_type = (
                    response.headers.get("Content-Type", "")
                    .split(";", 1)[0]
                    .strip()
                    .lower()
                )
                if content_type not in self.ALLOWED_CONTENT_TYPES:
                    response.release()
                    raise UnsupportedContentTypeError(
                        f"Unsupported Content-Type: {content_type or 'missing'}"
                    )

                try:
                    body = await read_limited_body(
                        response, self.max_response_bytes
                    )
                finally:
                    response.release()

                return FetchResult(
                    requested_url=requested_url,
                    final_url=current_url,
                    status=response.status,
                    content_type=content_type,
                    body=body,
                    fetched_at=datetime.now(timezone.utc),
                    elapsed_seconds=time.monotonic() - started,
                )

        raise FetchError("Fetcher exited without a response")

    async def _request_with_retries(
        self, session: aiohttp.ClientSession, url: str
    ) -> aiohttp.ClientResponse:
        for attempt in range(self.max_retries + 1):
            try:
                response = await session.get(url, allow_redirects=False)
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                if attempt >= self.max_retries:
                    raise FetchError(f"HTTP request failed: {exc}") from exc
                await asyncio.sleep(min(0.5 * (2**attempt), 2.0))
                continue

            if response.status not in self.RETRYABLE_STATUSES:
                return response

            retry_after = parse_retry_after(response.headers.get("Retry-After"))
            response.release()
            if attempt >= self.max_retries:
                raise FetchError(
                    f"Retryable HTTP status persisted: {response.status}"
                )

            delay = retry_after if retry_after is not None else min(
                0.5 * (2**attempt), 2.0
            )
            await asyncio.sleep(min(delay, self.max_retry_after_seconds))

        raise FetchError("HTTP retry loop exhausted")
