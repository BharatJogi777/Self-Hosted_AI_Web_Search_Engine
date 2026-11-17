from __future__ import annotations

from typing import Any

import httpx


class OllamaChatError(RuntimeError):
    """Raised when Ollama chat generation fails."""


class OllamaChatClient:
    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen3:4b",
        timeout_seconds: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds),
        )
        self._owns_client = client is None

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            response = await self._client.post(
                "/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "tools": tools,
                    "stream": False,
                },
            )
            response.raise_for_status()
            payload = response.json()
            message = payload.get("message")
            if not isinstance(message, dict):
                raise ValueError("Ollama response did not contain a message")
            return message
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise OllamaChatError(f"Ollama chat request failed: {exc}") from exc

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
