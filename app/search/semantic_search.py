from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.search.chunking import chunk_text
from app.search.ollama_embeddings import OllamaEmbeddingClient


@dataclass(frozen=True)
class IndexedDocument:
    page_id: UUID
    version_id: UUID
    chunk_count: int
    embedding_model: str


@dataclass(frozen=True)
class SemanticSearchResult:
    page_id: UUID
    version_id: UUID
    chunk_id: UUID
    url: str
    title: str
    domain: str
    content: str
    distance: float
    score: float


class SemanticSearchRepository:
    """Chunk indexing and cosine-distance retrieval against PostgreSQL pgvector."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        embeddings: OllamaEmbeddingClient,
        *,
        max_chunk_chars: int = 1200,
        chunk_overlap: int = 150,
        batch_size: int = 16,
    ) -> None:
        self._sessions = sessions
        self._embeddings = embeddings
        self._max_chunk_chars = max_chunk_chars
        self._chunk_overlap = chunk_overlap
        self._batch_size = batch_size

    async def index_document(self, page_id: UUID) -> IndexedDocument:
        async with self._sessions() as session:
            row = (await session.execute(text("""
                SELECT p.id AS page_id, pv.id AS version_id, pv.extracted_text
                FROM pages p
                JOIN page_versions pv
                  ON pv.page_id = p.id
                 AND pv.content_hash = p.current_content_hash
                WHERE p.id = :page_id
            """), {"page_id": page_id})).mappings().first()
        if row is None:
            raise LookupError("Document or its current content version was not found")

        chunks = chunk_text(
            row["extracted_text"],
            max_chars=self._max_chunk_chars,
            overlap=self._chunk_overlap,
        )
        vectors: list[list[float]] = []
        for offset in range(0, len(chunks), self._batch_size):
            batch = chunks[offset:offset + self._batch_size]
            vectors.extend(await self._embeddings.embed([item.content for item in batch]))

        async with self._sessions() as session:
            async with session.begin():
                # Re-indexing the same page version replaces its rows atomically.
                await session.execute(text("""
                    DELETE FROM page_chunks
                    WHERE page_version_id = :version_id
                      AND embedding_model = :model
                """), {"version_id": row["version_id"], "model": self._embeddings.model})
                for chunk, vector in zip(chunks, vectors, strict=True):
                    await session.execute(text("""
                        INSERT INTO page_chunks
                            (page_version_id, chunk_index, content, content_hash,
                             embedding_model, embedding)
                        VALUES
                            (:version_id, :chunk_index, :content, :content_hash,
                             :model, CAST(:embedding AS vector))
                    """), {
                        "version_id": row["version_id"],
                        "chunk_index": chunk.index,
                        "content": chunk.content,
                        "content_hash": chunk.content_hash,
                        "model": self._embeddings.model,
                        "embedding": _vector_literal(vector),
                    })

        return IndexedDocument(
            page_id=row["page_id"],
            version_id=row["version_id"],
            chunk_count=len(chunks),
            embedding_model=self._embeddings.model,
        )

    async def search(
        self, query: str, *, limit: int = 10, domain: str | None = None
    ) -> list[SemanticSearchResult]:
        cleaned = query.strip()
        if not cleaned:
            raise ValueError("query must not be empty")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")

        query_vectors = await self._embeddings.embed([cleaned])
        async with self._sessions() as session:
            rows = (await session.execute(text("""
                SELECT
                    p.id AS page_id,
                    pv.id AS version_id,
                    pc.id AS chunk_id,
                    p.normalized_url AS url,
                    COALESCE(NULLIF(pv.title_snapshot, ''), p.title, p.normalized_url) AS title,
                    p.domain,
                    pc.content,
                    (pc.embedding <=> CAST(:embedding AS vector)) AS distance
                FROM page_chunks pc
                JOIN page_versions pv ON pv.id = pc.page_version_id
                JOIN pages p ON p.id = pv.page_id
                WHERE pv.content_hash = p.current_content_hash
                  AND pc.embedding_model = :model
                  AND (:domain IS NULL OR p.domain = :domain)
                ORDER BY pc.embedding <=> CAST(:embedding AS vector)
                LIMIT :limit
            """), {
                "embedding": _vector_literal(query_vectors[0]),
                "model": self._embeddings.model,
                "domain": domain,
                "limit": limit,
            })).mappings().all()

        return [
            SemanticSearchResult(
                page_id=row["page_id"],
                version_id=row["version_id"],
                chunk_id=row["chunk_id"],
                url=row["url"],
                title=row["title"],
                domain=row["domain"],
                content=row["content"],
                distance=float(row["distance"]),
                score=max(0.0, 1.0 - float(row["distance"])),
            )
            for row in rows
        ]


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(format(value, ".9g") for value in vector) + "]"
