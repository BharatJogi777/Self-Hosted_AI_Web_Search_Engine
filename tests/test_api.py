import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import create_app


@pytest.mark.asyncio
async def test_liveness_endpoint():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_crawl_is_disabled_without_allowlist(monkeypatch):
    monkeypatch.delenv("ALLOWED_DOMAINS", raising=False)
    app = create_app()

    class FakeService:
        pass

    # ASGITransport does not run lifespan automatically; provide the state
    # dependency explicitly for this isolated route test.
    app.state.ingestion_service = None
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/crawl", json={"url": "https://example.com/"})
    assert response.status_code == 503
