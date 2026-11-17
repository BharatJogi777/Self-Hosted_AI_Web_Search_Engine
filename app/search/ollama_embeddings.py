from __future__ import annotations

import httpx


class EmbeddingError(RuntimeError):
    """Raised when Ollama cannot produce a valid embedding response."""


class OllamaEmbeddingClient:
    """Small async client for Ollama's /api/embed endpoint."""

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "nomic-embed-text",
        dimensions: int = 768,
        timeout_seconds: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self.model = model
        self.dimensions = dimensions
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds),
        )
        self._owns_client = client is None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if any(not value.strip() for value in texts):
            raise ValueError("embedding inputs must not be empty")

        try:
            response = await self._client.post(
                "/api/embed",
                json={"model": self.model, "input": texts},
            )
            response.raise_for_status()
            payload = response.json()
            vectors = payload["embeddings"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise EmbeddingError(f"Ollama embedding request failed: {exc}") from exc

        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise EmbeddingError("Ollama returned an unexpected number of embeddings")

        validated: list[list[float]] = []
        for vector in vectors:
            if not isinstance(vector, list) or len(vector) != self.dimensions:
                raise EmbeddingError(
                    f"Expected embedding dimension {self.dimensions}, got "
                    f"{len(vector) if isinstance(vector, list) else 'invalid'}"
                )
            try:
                converted = [float(value) for value in vector]
            except (TypeError, ValueError) as exc:
                raise EmbeddingError("Embedding contains a non-numeric value") from exc
            validated.append(converted)
        return validated

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
