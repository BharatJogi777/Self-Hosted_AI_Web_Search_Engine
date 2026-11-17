from __future__ import annotations

import hashlib


def cache_key(path: str, query_string: bytes) -> str:
    digest = hashlib.sha256(path.encode() + b"?" + query_string).hexdigest()
    return f"search-api:v1:{digest}"
