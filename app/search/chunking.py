from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    index: int
    content: str
    content_hash: str


def chunk_text(text: str, *, max_chars: int = 1200, overlap: int = 150) -> list[TextChunk]:
    """Split text into deterministic, overlapping chunks.

    Character limits are deliberately used instead of pretending to count model
    tokens. A tokenizer-specific splitter can replace this implementation later.
    """
    if max_chars < 100:
        raise ValueError("max_chars must be at least 100")
    if overlap < 0 or overlap >= max_chars:
        raise ValueError("overlap must be >= 0 and smaller than max_chars")

    normalized = " ".join(text.split())
    if not normalized:
        return []

    chunks: list[TextChunk] = []
    start = 0
    while start < len(normalized):
        end = min(start + max_chars, len(normalized))
        if end < len(normalized):
            boundary = normalized.rfind(" ", start + max_chars // 2, end)
            if boundary > start:
                end = boundary

        content = normalized[start:end].strip()
        if content:
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            chunks.append(TextChunk(len(chunks), content, digest))

        if end >= len(normalized):
            break
        next_start = max(start + 1, end - overlap)
        # Avoid starting in the middle of a word where a nearby boundary exists.
        whitespace = normalized.find(" ", next_start, min(next_start + 40, len(normalized)))
        start = whitespace + 1 if whitespace != -1 else next_start

    return chunks
