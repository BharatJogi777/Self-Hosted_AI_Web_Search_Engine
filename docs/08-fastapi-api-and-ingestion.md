# 08 — FastAPI Search API and Ingestion Workflow

## 1. Why introduce an API boundary?

The crawler, extractor, database, and search code should be reusable without being tied to HTTP. FastAPI is an adapter: it validates external input, calls application services, and translates results or failures into HTTP responses.

The dependency direction should remain:

```text
HTTP request
    |
    v
FastAPI route + Pydantic schema
    |
    v
Application service
    |                         |
    v                         v
Crawler / extractor       Repository
                              |
                              v
                         PostgreSQL
```

Do not put SQL statements, crawler loops, or HTML parsing directly inside route functions.

## 2. Endpoints

| Endpoint | Purpose |
|---|---|
| GET /health/live | Process liveness |
| GET /health/ready | Database readiness |
| POST /crawl | Crawl one URL inside the configured domain allowlist |
| GET /search | Full-text search with limit, offset, and optional domain |
| GET /documents | Paginated document listing |
| GET /documents/{document_id} | Retrieve one document's metadata |

Interactive API documentation is available at `/docs` when the server is running.

## 3. Configure and run

Install dependencies, start PostgreSQL, and apply migrations first. Configure the allowed crawl domains explicitly:

```bash
export DATABASE_URL='postgresql+asyncpg://search:search@localhost:5432/search_engine'
export ALLOWED_DOMAINS='example.com,docs.example.org'

alembic upgrade head
uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

The default bind address is loopback so the development API is not exposed to the network by accident. Configure authentication, TLS termination, rate limiting, and a deliberate network policy before exposing it.

## 4. Controlled ingestion and robots.txt

The ingestion service normalizes the submitted URL through the configured allowlist, retrieves that origin's robots.txt through the safe fetcher, checks the crawler user-agent's permission, fetches the page, extracts content, and persists it.

The implementation fails closed if robots.txt cannot be retrieved. This is deliberately conservative; a later crawler-policy module can distinguish robots status classes and implement caching and refresh rules.

The URL allowlist is not optional. If `ALLOWED_DOMAINS` is empty, the crawl endpoint returns 503. The crawler fetcher also validates DNS results and redirect targets. These controls reduce SSRF risk but do not replace network-level egress restrictions.

## 5. Search API example

```bash
curl 'http://127.0.0.1:8000/search?q=distributed%20systems&limit=10'
```

Optional parameters:
- `limit`: 1–100, default 10.
- `offset`: zero or greater, default 0.
- `domain`: exact hostname filter.

The SQL uses bound parameters. The API validates query length and pagination values. Add authentication and per-client rate limits before allowing public traffic.

## 6. Crawl API example

```bash
curl -X POST 'http://127.0.0.1:8000/crawl' \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com/"}'
```

The submitted host must be covered by `ALLOWED_DOMAINS`. The service does not accept arbitrary local, private, IP-literal, or out-of-scope destinations. A successful response reports whether a page was created and whether a new content version was stored.

## 7. Production considerations

This module intentionally performs a single crawl synchronously inside the request. It is useful for learning and small controlled corpora, but it is not a durable crawl queue. Production ingestion should enqueue jobs, use worker processes, persist crawl state, enforce distributed per-host rate limits, and provide cancellation and retry policies.

Other required hardening:
- Authentication and authorization for crawl operations.
- API-level rate limits and request-size limits.
- Structured logs and request/crawl correlation IDs.
- Database pool sizing and statement timeouts.
- Network egress restrictions in addition to DNS checks.
- Robots.txt cache with expiry and explicit handling of 2xx, 3xx, 4xx, and 5xx responses.
- Sanitization/escaping of snippets before rendering HTML.
- PostgreSQL integration tests for migrations and full-text queries.

## 8. Exercises

1. Run the API locally and inspect the generated OpenAPI schema at `/openapi.json`.
2. Try an out-of-scope URL and confirm the crawl endpoint rejects it.
3. Crawl the same unchanged page twice and compare `content_changed`.
4. Change the page content and verify a new page version is created.
5. Search by phrase and by domain.
6. Add authentication to `POST /crawl` without changing the search repository.

## 9. Next module

Next we will introduce a durable crawl job model and worker architecture so a user request enqueues work rather than holding an HTTP connection open while crawling.
