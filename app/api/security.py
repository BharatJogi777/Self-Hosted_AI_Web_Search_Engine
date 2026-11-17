from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException, Request, status


def configured_api_keys() -> tuple[str, ...]:
    return tuple(
        value.strip()
        for value in os.getenv("API_KEYS", "").split(",")
        if value.strip()
    )


async def require_api_key(
    request: Request,
    supplied_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    keys = getattr(request.app.state, "api_keys", configured_api_keys())
    if not keys:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API authentication is not configured",
        )
    if supplied_key is None or not any(
        hmac.compare_digest(supplied_key, configured) for configured in keys
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid X-API-Key header is required",
            headers={"WWW-Authenticate": "ApiKey"},
        )
