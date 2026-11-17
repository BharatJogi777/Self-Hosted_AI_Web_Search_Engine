import asyncio
from types import SimpleNamespace

import pytest

from app.crawler.fetcher import (
    HostRateLimiter,
    PublicOnlyResolver,
    ResponseTooLargeError,
    is_public_ip,
    parse_retry_after,
    read_limited_body,
)


@pytest.mark.parametrize(
    "address",
    ["8.8.8.8", "1.1.1.1", "2606:4700:4700::1111"],
)
def test_public_ip_is_accepted(address: str) -> None:
    assert is_public_ip(address)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.10",
        "169.254.169.254",
        "::1",
        "fe80::1",
        "224.0.0.1",
        "not-an-ip",
    ],
)
def test_non_public_ip_is_rejected(address: str) -> None:
    assert not is_public_ip(address)


@pytest.mark.asyncio
async def test_resolver_rejects_private_dns_answer(monkeypatch) -> None:
    async def fake_getaddrinfo(*args, **kwargs):
        return [
            (2, 1, 6, "", ("127.0.0.1", 443)),
        ]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", fake_getaddrinfo)
    resolver = PublicOnlyResolver()

    with pytest.raises(Exception, match="non-public"):
        await resolver.resolve("public-looking.example", 443)


class FakeContent:
    def __init__(self, chunks):
        self.chunks = chunks

    async def iter_chunked(self, size):
        for chunk in self.chunks:
            yield chunk


@pytest.mark.asyncio
async def test_read_limited_body_returns_content() -> None:
    response = SimpleNamespace(
        headers={"Content-Length": "5"},
        content=FakeContent([b"he", b"llo"]),
    )
    assert await read_limited_body(response, 10) == b"hello"


@pytest.mark.asyncio
async def test_read_limited_body_rejects_oversized_stream() -> None:
    response = SimpleNamespace(
        headers={},
        content=FakeContent([b"1234", b"5678"]),
    )
    with pytest.raises(ResponseTooLargeError):
        await read_limited_body(response, 5)


@pytest.mark.asyncio
async def test_read_limited_body_rejects_oversized_content_length() -> None:
    response = SimpleNamespace(
        headers={"Content-Length": "100"},
        content=FakeContent([]),
    )
    with pytest.raises(ResponseTooLargeError):
        await read_limited_body(response, 10)


def test_retry_after_seconds() -> None:
    assert parse_retry_after("3") == 3.0
    assert parse_retry_after(None) is None


def test_rate_limiter_rejects_negative_interval() -> None:
    with pytest.raises(ValueError):
        HostRateLimiter(-1)
