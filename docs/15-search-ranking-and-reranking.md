# Module 15 — Search Ranking and Reranking

## 1. Retrieval is not the same as ranking

A search engine has two distinct jobs:

1. **Candidate retrieval:** Find a reasonably broad set of potentially relevant pages quickly.
2. **Reranking:** Spend more computation comparing those candidates and order the strongest matches first.

Our hybrid retriever already performs candidate retrieval:
- PostgreSQL full-text search finds lexical matches.
- pgvector finds semantically similar chunks.
- Reciprocal Rank Fusion (RRF) merges those result lists at page level.

The new reranking stage examines up to a configurable number of hybrid candidates and returns the best results.

## 2. Ranking signals

The baseline uses four transparent signals:

| Signal | Meaning |
|---|---|
| Normalized RRF | How highly the page ranked across lexical and semantic retrieval |
| Title coverage | Fraction of query terms found in the title |
| Snippet coverage | Fraction of query terms found in the returned passage/snippet |
| Exact title phrase | Whether the normalized query phrase appears in the title |

The score is:

```text
score = 0.55 * normalized_rrf
      + 0.25 * title_coverage
      + 0.15 * snippet_coverage
      + 0.05 * exact_title_match
```

The normalized RRF value divides the fusion score by the maximum theoretical contribution from two rank-1 retrievers, using the configured RRF constant. The result is capped at 1.

These weights are an initial engineering baseline, not universal relevance truths. They must be evaluated against judged queries before production use.

## 3. Why title matches matter

For technical search, a page whose title contains all query terms is often a stronger result than a page that mentions the terms once in a long body. This is especially useful for:
- API and framework documentation
- Error codes and technical identifiers
- Product and project names
- Troubleshooting guides

This baseline tokenizes terms case-insensitively. It deliberately does not implement language-specific stemming, synonym expansion, typo correction, or sophisticated phrase parsing. PostgreSQL's English full-text configuration handles its own lexical normalization independently.

## 4. API

The new endpoint is:

```http
GET /search/reranked?q=postgres%20connection%20pool&limit=10
```

Optional domain filter:

```bash
curl --get http://localhost:8000/search/reranked \
  --data-urlencode 'q=postgres connection pool' \
  --data-urlencode 'domain=docs.example.com' \
  --data-urlencode 'limit=10'
```

Configuration:
- `HYBRID_RRF_K`: RRF smoothing constant (default 60).
- `HYBRID_CANDIDATE_LIMIT`: candidate count retrieved before reranking (default 50).
- `RERANK_CANDIDATE_LIMIT`: candidate count used by the reranked endpoint (default 50).

Increasing candidate depth may improve recall but also increases reranking work. Keep it bounded and measure latency.

## 5. Reranker interface and future cross-encoders

`Reranker` is a small protocol. The current `TermCoverageReranker` is deterministic, fast, explainable, and requires no model download.

A learned cross-encoder can later implement the same interface. A cross-encoder receives a pair such as:

```text
(query, candidate title + passage)
```

It jointly processes both texts and predicts a relevance score. Unlike bi-encoder retrieval, it does not precompute one vector per document, so it is more expensive and should run only on a bounded candidate set.

Do not confuse these components:
- **Embedding model / bi-encoder:** independently encodes query and document for vector retrieval.
- **Cross-encoder:** jointly scores a query-document pair for reranking.
- **Ollama chat model:** generates text; it is not automatically a relevance cross-encoder.

A cross-encoder is intentionally not a mandatory dependency here. Many models consume significant RAM and may be slow on an 8 GB laptop. First establish a relevance evaluation set and measure whether the extra model improves quality enough to justify its cost.

## 6. BM25 versus PostgreSQL full-text ranking

The current lexical retriever uses PostgreSQL `ts_rank_cd` over a weighted `tsvector`. This is PostgreSQL's ranking function; it is **not BM25**.

BM25 is a separate probabilistic ranking function that accounts for term frequency, inverse document frequency, and document length normalization. We should not label `ts_rank_cd` as BM25. A future module can compare a true BM25 implementation against PostgreSQL FTS using the same judged query set.

## 7. Tests

Run:

```bash
pytest -q tests/test_ranking.py tests/test_hybrid_search.py
```

These tests cover deterministic scoring and ordering with in-memory candidates. They do not validate relevance against a real corpus, PostgreSQL, pgvector, or Ollama. Module 16 introduces a reproducible relevance-evaluation dataset and metrics.

## 8. Production cautions

- A ranking score is not a probability or calibrated confidence.
- Query-term overlap is language-agnostic only at a very basic token level.
- Snippets are not necessarily full document text.
- Candidate retrieval limits cap what the reranker can discover.
- The API still needs authentication, quotas, and operational protection before public exposure.
- Tune weights only with relevance judgments, not intuition alone.
