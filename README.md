# Self-Hosted AI Web Search Engine

A learning and engineering project to build a self-hosted web search service that can crawl permitted websites, extract content, index pages, retrieve relevant results, and provide grounded context to LLM applications.

## Project goals

- Build a crawler with explicit scope, politeness controls, and robots.txt handling.
- Extract and normalize useful page content.
- Store pages and searchable representations in PostgreSQL.
- Implement lexical search first, then semantic and hybrid retrieval.
- Rank results and return source URLs and snippets.
- Expose the engine through FastAPI.
- Integrate with Ollama, LangChain, and MCP after the search core works.
- Test, observe, secure, and deploy the system with Docker Compose.

This project is not intended to reproduce Google's global index. The initial search corpus will be a controlled set of permitted domains and URLs.

## Learning sequence

1. [Architecture](docs/01-architecture.md)
2. Search engine fundamentals
3. Web crawling and URL safety
4. HTTP fetching and politeness
5. HTML content extraction
6. Document storage and versioning
7. PostgreSQL full-text search
8. FastAPI API and ingestion
9. Durable crawl queue and workers
10. Worker reliability and observability
11. Distributed crawling and politeness
12. Sitemap discovery and bounded crawl runs
13. Semantic search with Ollama and pgvector
14. Hybrid search and Reciprocal Rank Fusion
15. Search ranking and reranking
16. Search quality evaluation
17. Query understanding, spelling correction, and suggestions
18. Production API security, caching, and rate limiting
19. Docker Compose deployment, monitoring, and performance
20. LLM integration, MCP server, and production capstone

## Planned technology

- Python 3.12+
- FastAPI + Uvicorn
- PostgreSQL 16 and pgvector
- PostgreSQL full-text search
- aiohttp, BeautifulSoup, Trafilatura
- Ollama for local embeddings and generation
- LangChain and MCP for agent integration
- pytest and Docker Compose

## Module 13 — Semantic search

See [Semantic search with Ollama and pgvector](docs/13-semantic-search-with-ollama-and-pgvector.md).

The API provides `POST /documents/{document_id}/index` to embed a document's current version and `GET /search/semantic?q=...` for semantic retrieval. Configure `OLLAMA_BASE_URL`, `EMBEDDING_MODEL`, and `EMBEDDING_DIMENSIONS`. The initial schema is fixed at 768 dimensions.

## Module 14 — Hybrid search

See [Hybrid Search and Reciprocal Rank Fusion](docs/14-hybrid-search-and-reciprocal-rank-fusion.md).

The `GET /search/hybrid` endpoint fuses lexical and semantic candidate rankings using RRF. Configure `HYBRID_RRF_K` (default 60) and `HYBRID_CANDIDATE_LIMIT` (default 50).

## Module 15 — Ranking and reranking

See [Search Ranking and Reranking](docs/15-search-ranking-and-reranking.md).

The `GET /search/reranked` endpoint retrieves hybrid candidates and reorders them using normalized RRF, title-term coverage, snippet-term coverage, and exact title phrase matching. Configure `RERANK_CANDIDATE_LIMIT` (defaults to `HYBRID_CANDIDATE_LIMIT`, which defaults to 50). The baseline is deterministic and has no additional model dependency.

## Module 16 — Search quality evaluation

See [Search Quality Evaluation](docs/16-search-quality-evaluation.md).

The offline evaluator computes Precision@k, Recall@k, MRR@k, MAP@k, and NDCG@k from human relevance judgments. Start with `python scripts/evaluate_search.py`; replace the synthetic starter judgments and sample run with results from your own corpus. These sample metrics are illustrative, not a real benchmark.

## Module 17 — Query understanding

See [Query Understanding and Search Suggestions](docs/17-query-understanding-and-suggestions.md).

The reranked search endpoint now applies conservative dictionary-based spelling correction and controlled synonym expansion. It returns the normalized, corrected, and expanded query alongside results. Use `GET /search/suggestions?q=...` for spelling suggestions. The starter vocabulary is intentionally small and should be expanded using reviewed corpus terms.

## Important crawler safeguards

The crawler must identify itself, respect robots.txt and site terms, apply per-host rate limits, use bounded timeouts and response sizes, avoid private or local network addresses, and provide a way to stop or exclude crawling. Do not bypass authentication, paywalls, CAPTCHAs, or access controls.

## Current implementation

- Scoped URL policy and bounded asynchronous HTTP fetcher.
- HTML extraction and content hashing.
- PostgreSQL page/version persistence and Alembic migrations.
- PostgreSQL full-text search with weighted title/body vectors.
- FastAPI endpoints for health, controlled crawling, search, document metadata, and durable crawl-job submission/status.
- PostgreSQL-backed crawl queue with worker leases, retry backoff, and independent worker process.
- Worker lease heartbeat, configurable concurrency, graceful shutdown, JSON logs, and Prometheus metrics.
- PostgreSQL-backed domain leases for cross-process crawl coordination.
- Bounded sitemap-index traversal, same-host HTML link discovery, and PostgreSQL-backed crawl runs with atomic page/depth budgets.
- Semantic retrieval using Ollama embeddings and pgvector.
- Hybrid lexical/semantic retrieval using Reciprocal Rank Fusion.
- Two-stage ranking with a lightweight reranking baseline.
- API-key protection for crawl/index operations, search rate limiting, and optional Redis-backed search response caching.
- Docker Compose deployment with PostgreSQL/pgvector, Redis, migration job, API, crawl worker, optional Prometheus, and an asynchronous search load-test utility.

The project is under active development. Run the test suite and apply migrations against PostgreSQL before relying on the implementation in production.

## Module 18 — API security and traffic controls

See [Production API Security, Caching, and Rate Limiting](docs/18-production-api-security-caching-rate-limiting.md). Administrative crawl and indexing routes require an `X-API-Key` configured through `API_KEYS`. Search routes are rate limited; configure Redis with `REDIS_URL` for shared rate limits and short-lived search response caching. The in-memory limiter is development-only.

## Module 19 — Deployment and performance

See [Docker Compose, Monitoring, and Performance](docs/19-docker-compose-monitoring-performance.md). Copy `.env.example` to `.env`, configure the database password, API key, and permitted crawl domains, then run `docker compose up --build -d`. Add `--profile observability` to start Prometheus. Ollama is expected to run on the host and is reached at `host.docker.internal` by default.
