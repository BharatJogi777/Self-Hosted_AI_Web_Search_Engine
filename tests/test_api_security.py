import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import create_app
from app.api.rate_limit import FixedWindowRateLimiter
from app.api.security import configured_api_keys


def test_configured_api_keys_are_trimmed(monkeypatch):
    monkeypatch.setenv("API_KEYS", " alpha , beta ,, ")
    assert configured_api_keys() == ("alpha", "beta")


@pytest.mark.asyncio
async def test_local_rate_limiter_blocks_after_limit():
    limiter = FixedWindowRateLimiter(limit=2, window_seconds=60)
    assert (await limiter.check("client")).allowed
    assert (await limiter.check("client")).allowed
    blocked = await limiter.check("client")
    assert not blocked.allowed
    assert blocked.retry_after >= 1


@pytest.mark.asyncio
async def test_crawl_requires_api_key(monkeypatch):
    monkeypatch.setenv("API_KEYS", "test-secret")
    monkeypatch.delenv("ALLOWED_DOMAINS", raising=False)
    app = create_app()
    app.state.api_keys = ("test-secret",)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        missing = await client.post("/crawl", json={"url": "https://example.com/"})
        invalid = await client.post(
            "/crawl", json={"url": "https://example.com/"},
            headers={"X-API-Key": "wrong"},
        )
        valid = await client.post(
            "/crawl", json={"url": "https://example.com/"},
            headers={"X-API-Key": "test-secret"},
        )
    assert missing.status_code == 401
    assert invalid.status_code == 401
    # Authentication succeeds; crawling is then rejected because no domain allowlist exists.
    assert valid.status_code == 503


@pytest.mark.asyncio
async def test_liveness_endpoint():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
