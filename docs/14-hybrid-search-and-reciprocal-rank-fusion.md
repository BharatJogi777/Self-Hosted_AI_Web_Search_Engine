# Module 14 — Hybrid Search and Reciprocal Rank Fusion

## 1. Why hybrid retrieval?

Lexical retrieval is particularly useful for exact names, product identifiers, error codes, API symbols, and quoted phrases. Semantic retrieval can find related passages even when the wording differs. Neither method dominates every query.

Hybrid retrieval runs both systems and combines their ranked candidates.

## 2. Why not add the raw scores?

PostgreSQL `ts_rank_cd` and vector cosine similarity are different signals with different ranges and distributions. Adding them directly (for example, `fts_score + cosine_score`) gives arbitrary influence to whichever score happens to have the larger numeric scale.

Reciprocal Rank Fusion (RRF) avoids that problem by using rank positions:

```text
RRF(document) = sum over retrievers [ 1 / (k + rank(document)) ]
```

A document ranked first by both retrievers receives two contributions. A document ranked highly by only one receives one contribution. The default constant is `k = 60`, a commonly used smoothing value. It is a tunable parameter, not a universal optimum.

## 3. Current implementation

The `HybridSearchRepository`:
1. Validates query and requested result limit.
2. Runs PostgreSQL full-text search and pgvector semantic search concurrently.
3. Retrieves up to 50 candidates from each retriever by default.
4. Converts each list position into an RRF contribution.
5. Combines candidates at page level, so several matching chunks do not create duplicate page results.
6. Returns the fused ranking, each retriever's rank, and a useful passage snippet.

The semantic passage is preferred for the returned snippet when a page appears in both lists. The RRF score is a ranking score, not a probability.

## 4. API

```bash
curl --get http://localhost:8000/search/hybrid \
  --data-urlencode 'q=postgres connection pool saturation' \
  --data-urlencode 'limit=10'
```

Optional domain filter:

```bash
curl --get http://localhost:8000/search/hybrid \
  --data-urlencode 'q=API latency' \
  --data-urlencode 'domain=docs.example.com'
```

The page must have been crawled for lexical retrieval and indexed through `POST /documents/{document_id}/index` for semantic retrieval. If one side has no candidates, the other side can still contribute results.

## 5. Important ranking details

- RRF uses ranks, not raw relevance values.
- Candidate depth matters: a relevant page outside both candidate windows cannot be fused.
- The default candidate window is 50 per retriever; benchmark and tune it.
- Results are deduplicated by page ID.
- A stable page-ID tie-breaker makes equal scores deterministic.
- Domain filtering is applied independently in both retrieval systems.
- The endpoint runs both retrieval paths concurrently. Ollama embedding latency and PostgreSQL query latency both contribute to total latency.

## 6. Evaluation exercises

Build a small query set containing:
- Exact technical identifiers, such as `SQLSTATE 23505`.
- Natural-language questions with synonyms.
- Named entities and product names.
- Queries containing quoted phrases.
- Queries where only lexical or only semantic retrieval is expected to perform well.

For each query, label the relevant pages and compare:
1. Lexical-only ranking.
2. Semantic-only ranking.
3. Hybrid RRF ranking.

Measure Recall@K, Precision@K, Mean Reciprocal Rank (MRR), and nDCG in the next evaluation module. Do not choose RRF parameters based only on a few hand-picked examples.

## 7. Operational caveats

This module provides a simple page-level fusion baseline. It does not yet implement learned ranking, cross-encoder reranking, query classification, per-field boosts, personalization, or click feedback. The lexical and semantic candidate limits should be configured based on measured latency and recall.

The API currently has no authentication. Protect it before exposing it beyond a trusted development network.

## 8. Tests

Run:

```bash
pytest -q tests/test_hybrid_search.py
```

These tests validate the RRF algorithm and deterministic behavior. They do not exercise PostgreSQL full-text search, pgvector, Ollama, or end-to-end API behavior. Those need integration tests with the real dependencies.
