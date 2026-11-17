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
2. [Search engine fundamentals](docs/02-search-engine-fundamentals.md)
3. Web crawling
4. Content extraction
5. Indexing and PostgreSQL full-text search
6. Semantic search with embeddings and pgvector
7. Hybrid retrieval
8. Ranking and reranking
9. [FastAPI search API and ingestion](docs/08-fastapi-api-and-ingestion.md)
10. [Durable crawl queue and workers](docs/09-durable-crawl-queue-and-workers.md)
11. [Worker reliability and observability](docs/10-worker-reliability-and-observability.md)
12. Distributed crawling and politeness
13. Semantic and hybrid search
14. LangChain and MCP integration

## Planned technology

- Python 3.12+
- FastAPI + Uvicorn
- PostgreSQL 16 and pgvector
- PostgreSQL full-text search
- aiohttp, BeautifulSoup, Trafilatura
- Ollama for local embeddings and generation
- LangChain and MCP for agent integration
- pytest and Docker Compose

Exact dependency versions will be pinned as implementation begins.

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

The project is under active development. Run the test suite and apply migrations against PostgreSQL before relying on the implementation in production.
