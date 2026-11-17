from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import get_close_matches
from typing import Mapping, Sequence


_TOKEN_RE = re.compile(r"[\w.+#-]+", re.UNICODE)


@dataclass(frozen=True)
class ProcessedQuery:
    original: str
    normalized: str
    corrected: str
    expanded: str
    corrections: tuple[tuple[str, str], ...]
    expansions: tuple[str, ...]


class QueryProcessor:
    """Conservative, dictionary-driven query processing.

    It does not call an LLM or external service. Unknown terms are preserved.
    Only configured vocabulary is eligible for spelling correction and
    synonym expansion, preventing speculative rewrites of technical terms.
    """

    def __init__(
        self,
        *,
        vocabulary: Sequence[str] = (),
        synonyms: Mapping[str, Sequence[str]] | None = None,
        correction_cutoff: float = 0.88,
        max_expansions: int = 3,
    ) -> None:
        if not 0.5 <= correction_cutoff <= 1.0:
            raise ValueError("correction_cutoff must be between 0.5 and 1")
        if max_expansions < 0:
            raise ValueError("max_expansions cannot be negative")
        self._vocabulary = tuple(sorted({word.casefold() for word in vocabulary}))
        self._synonyms = {
            key.casefold(): tuple(value.casefold() for value in values)
            for key, values in (synonyms or {}).items()
        }
        self._cutoff = correction_cutoff
        self._max_expansions = max_expansions

    def process(self, query: str) -> ProcessedQuery:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must not be empty")
        normalized = " ".join(query.split())
        tokens = _TOKEN_RE.findall(normalized)
        corrections: list[tuple[str, str]] = []
        corrected_tokens: list[str] = []

        vocabulary = set(self._vocabulary)
        for token in tokens:
            folded = token.casefold()
            replacement = token
            # Preserve short tokens, identifiers, versions, and punctuation-rich terms.
            if (
                vocabulary
                and len(folded) >= 5
                and folded.isalpha()
                and folded not in vocabulary
            ):
                matches = get_close_matches(
                    folded, self._vocabulary, n=1, cutoff=self._cutoff
                )
                if matches:
                    replacement = matches[0]
                    corrections.append((token, replacement))
            corrected_tokens.append(replacement)

        corrected = " ".join(corrected_tokens)
        expansions: list[str] = []
        seen = {token.casefold() for token in corrected_tokens}
        for token in corrected_tokens:
            for synonym in self._synonyms.get(token.casefold(), ()):
                if synonym not in seen and len(expansions) < self._max_expansions:
                    expansions.append(synonym)
                    seen.add(synonym)

        expanded = corrected
        if expansions:
            expanded = f"{corrected} {' '.join(expansions)}"

        return ProcessedQuery(
            original=query,
            normalized=normalized,
            corrected=corrected,
            expanded=expanded,
            corrections=tuple(corrections),
            expansions=tuple(expansions),
        )

    def suggest(self, query: str, *, limit: int = 5) -> list[str]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must not be empty")
        if not 1 <= limit <= 10:
            raise ValueError("limit must be between 1 and 10")
        if not self._vocabulary:
            return []
        tokens = _TOKEN_RE.findall(" ".join(query.split()))
        if not tokens:
            return []
        last = tokens[-1].casefold()
        matches = get_close_matches(
            last, self._vocabulary, n=limit, cutoff=self._cutoff
        )
        return [*matches]


def default_query_processor() -> QueryProcessor:
    """Small starter dictionary; replace/extend with corpus-derived vocabulary."""
    return QueryProcessor(
        vocabulary=(
            "postgresql", "database", "connection", "pooling", "python",
            "asyncio", "fastapi", "validation", "vector", "similarity",
            "search", "crawler", "distributed", "worker", "retries",
            "embedding", "reranking", "microservices", "kubernetes",
        ),
        synonyms={
            "postgresql": ("postgres",),
            "postgres": ("postgresql",),
            "pooling": ("pool",),
            "vector": ("embedding",),
            "crawler": ("spider",),
        },
    )
