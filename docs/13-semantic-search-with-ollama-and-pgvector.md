# Module 13 — Semantic Search with Ollama and pgvector

## 1. Why semantic search?

Lexical search answers: "Which documents contain these words?" Semantic search answers: "Which passages discuss a similar idea, even if they use different words?"

For example, a query such as "how do I make an API respond faster?" may be relevant to a passage titled "Reducing request latency" even when the exact query words are absent.

An embedding model converts text into a numeric vector. Similarity between vectors is used as a retrieval signal. An embedding is not a summary and does not prove that two passages are equivalent.

## 2. Data flow

1. A crawler stores an immutable page version.
2. The indexer reads the current version's extracted text.
3. The chunker splits it into bounded, overlapping passages.
4. Ollama converts each passage into an embedding.
5. PostgreSQL stores passage text and its vector in `page_chunks`.
6. A search request embeds the query and orders matching current-version chunks by cosine distance.

Old page versions remain in the database, but semantic retrieval filters to the page's current content hash.

## 3. Why chunk documents?

Embedding an entire long page into one vector can blur several topics. Chunking creates smaller retrieval units with enough surrounding context.

This implementation uses a deterministic character-based splitter:
- Default maximum chunk size: 1,200 characters.
- Default overlap: 150 characters.
- Paragraph whitespace is normalized.
- Each chunk receives a SHA-256 content hash.

Character count is only an approximation. It is not a token count. A future tokenizer-aware splitter can replace it without changing the retrieval architecture.

## 4. Ollama setup

Install/pull the embedding model on the machine running Ollama:

```bash
ollama pull nomic-embed-text
ollama list
```

The service calls Ollama's `POST /api/embed` endpoint with a batch of input strings. The default configuration expects 768 dimensions.

Environment variables:

```bash
export OLLAMA_BASE_URL=http://127.0.0.1:11434
export EMBEDDING_MODEL=nomic-embed-text
export EMBEDDING_DIMENSIONS=768
```

If the API runs inside Docker on macOS while Ollama runs on the host, the base URL will generally need to use `http://host.docker.internal:11434`. Do not expose Ollama publicly without network controls.

## 5. PostgreSQL and pgvector

The PostgreSQL server must have pgvector installed. The migration enables the extension and creates a 768-dimensional vector column plus an HNSW cosine index.

Apply migrations only after confirming the PostgreSQL installation supports pgvector:

```bash
alembic upgrade head
```

The vector dimension is a schema decision. If you change to a model with a different output dimension, update the migration/schema and configuration together. Do not silently truncate or pad vectors.

## 6. API

Index the current version of a stored document:

```bash
curl -X POST http://localhost:8000/documents/<PAGE_UUID>/index
```

Search semantically:

```bash
curl --get http://localhost:8000/search/semantic \
  --data-urlencode 'q=how can I reduce API latency' \
  --data-urlencode 'limit=5'
```

The result's `distance` is cosine distance (lower is closer). The returned `score` is a convenience transformation `1 - distance`; it is not a calibrated probability or relevance percentage.

## 7. Operational considerations

- Embedding calls are batched to avoid sending an entire large document in one request.
- Re-indexing the same page version and model replaces its chunks atomically.
- The database unique constraint prevents duplicate chunk rows for the same version/index/model.
- The HNSW index is approximate; recall and latency must be measured on a representative corpus.
- A model change requires re-embedding the corpus. Keep model names explicit in stored rows.
- This module indexes on an explicit API request. It does not yet automatically embed every crawl result.
- There is no authentication on the API yet. Do not expose indexing endpoints to an untrusted network.
- The first version does not implement deletion policies, embedding job queues, model migrations, or hybrid ranking.

## 8. Tests and validation

Run unit tests:

```bash
pip install -r requirements.txt
pytest -q
```

The unit tests cover chunk boundaries, stable hashes, input validation, the Ollama request shape, and embedding dimension checks. They do not prove that pgvector is installed, that the migration applies, or that semantic ranking behaves correctly against PostgreSQL. Those require integration tests against a real pgvector-enabled PostgreSQL instance.
