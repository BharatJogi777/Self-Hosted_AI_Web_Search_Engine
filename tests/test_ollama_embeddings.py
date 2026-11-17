import httpx
import pytest

from app.search.ollama_embeddings import EmbeddingError, OllamaEmbeddingClient


@pytest.mark.asyncio
async def test_embedding_client_posts_batch_and_validates_dimensions():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2], [0.3, 0.4]]})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(base_url="http://ollama.test", transport=transport)
    embeddings = OllamaEmbeddingClient(
        model="test-embed", dimensions=2, client=client
    )

    result = await embeddings.embed(["first text", "second text"])

    assert result == [[0.1, 0.2], [0.3, 0.4]]
    assert seen["path"] == "/api/embed"
    assert '"model":"test-embed"' in seen["body"]
    await client.aclose()


@pytest.mark.asyncio
async def test_embedding_client_rejects_wrong_dimensions():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"embeddings": [[0.1]]})
    )
    client = httpx.AsyncClient(base_url="http://ollama.test", transport=transport)
    embeddings = OllamaEmbeddingClient(model="test", dimensions=2, client=client)

    with pytest.raises(EmbeddingError, match="dimension"):
        await embeddings.embed(["text"])
    await client.aclose()


@pytest.mark.asyncio
async def test_embedding_client_rejects_empty_inputs():
    client = OllamaEmbeddingClient(
        model="test", dimensions=2,
        client=httpx.AsyncClient(base_url="http://ollama.test"),
    )
    with pytest.raises(ValueError):
        await client.embed([""])
    await client._client.aclose()
