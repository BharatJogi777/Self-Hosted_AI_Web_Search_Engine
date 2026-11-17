# Module 19 — Docker Compose, Monitoring, and Performance

## 1. Deployment topology

The Compose stack separates responsibilities:

- **db** — PostgreSQL 16 with pgvector and a persistent volume.
- **redis** — shared rate-limit counters and short-lived search response cache.
- **migrate** — one-shot Alembic migration job; API and worker wait for it to complete successfully.
- **api** — FastAPI/Uvicorn HTTP service.
- **worker** — independent crawl queue consumer and Prometheus metrics exporter.
- **prometheus** — optional metrics collector enabled with the `observability` profile.

Ollama is intentionally not containerized in this setup. On an 8 GB Apple Silicon Mac, run Ollama on the host and let the API reach it through `host.docker.internal`. The worker does not need Ollama for crawling.

## 2. Files added

- `Dockerfile` — Python 3.12 slim image, installs pinned-range requirements, runs as non-root.
- `docker-compose.yml` — services, health checks, dependencies, persistent volumes and conservative resource limits.
- `.dockerignore` — excludes local environments, Git data, and secrets from build context.
- `.env.example` — deployment configuration template.
- `monitoring/prometheus.yml` — scrapes worker metrics.
- `scripts/load_test.py` — small asynchronous API load/smoke test.

## 3. First-time setup

Install Docker Desktop, then from the repository root:

```bash
cp .env.example .env
```

Edit `.env`. Set a strong database password and API key. A URL-safe password can be generated with:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Set `ALLOWED_DOMAINS` to domains you are permitted to crawl, without scheme or path. For example, `example.com,docs.example.org`.

Make sure Ollama is running on the Mac host and that the configured embedding model is available:

```bash
ollama pull nomic-embed-text
ollama list
```

Start the core stack:

```bash
docker compose up --build -d
```

Start optional Prometheus monitoring:

```bash
docker compose --profile observability up --build -d
```

The migration service runs `alembic upgrade head` before the API and worker start. Check service state and logs:

```bash
docker compose ps
docker compose logs -f migrate api worker
```

## 4. Verify the deployment

Liveness and readiness:

```bash
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
```

Submit a crawl job (replace the URL with a permitted site):

```bash
curl -X POST http://localhost:8000/crawl-jobs \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com/"}'
```

Search:

```bash
curl --get http://localhost:8000/search \
  --data-urlencode "q=example documentation"
```

When the observability profile is active, open Prometheus at `http://localhost:9090`. Useful worker metrics include:

- `search_crawl_jobs_claimed_total`
- `search_crawl_jobs_completed_total`
- `search_crawl_jobs_failed_total`
- `search_crawl_active_workers`
- `search_crawl_pending_jobs`
- `search_crawl_running_jobs`
- `search_crawl_job_duration_seconds`

Prometheus currently scrapes the worker exporter. The API itself does not yet expose application metrics.

## 5. Load-test the search endpoint

Install requirements in your local virtual environment, then run:

```bash
python scripts/load_test.py \
  --base-url http://localhost:8000 \
  --endpoint /search \
  --query "postgres indexing" \
  --requests 100 \
  --concurrency 5
```

The script reports throughput, status counts, and p50/p95/p99 latency. The default rate limit is 60 requests per 60 seconds per client IP, so increase it temporarily for a controlled benchmark or use a request count that stays within the configured limit. Do not benchmark a public service without permission.

This is a basic smoke/load tool, not a substitute for a full load-testing system. Run multiple test levels and record the database size, hardware, concurrency, cache state, and query mix so measurements can be compared fairly.

## 6. Performance tuning sequence

Tune one bottleneck at a time:

1. Establish a baseline with a representative query set and cold/warm cache runs.
2. Inspect PostgreSQL with `EXPLAIN (ANALYZE, BUFFERS)` for lexical and vector queries.
3. Check index usage, sequential scans, row estimates, and buffer reads.
4. Measure Ollama embedding latency separately from database retrieval.
5. Adjust `HYBRID_CANDIDATE_LIMIT`, `RERANK_CANDIDATE_LIMIT`, and API result limits only after evaluating search quality.
6. Tune worker concurrency and per-domain crawl politeness together; more workers must not violate site rate limits.
7. Watch database connection counts and pool wait time before increasing API replicas.
8. Keep Redis cache TTL short enough that newly crawled content becomes visible promptly.

Do not optimize only for throughput. Compare the Module 16 relevance metrics when changing candidate counts, chunking, ranking, or reranking.

## 7. Operations and data safety

- `postgres_data` and `redis_data` are named volumes; container replacement does not remove them.
- `docker compose down` stops and removes containers/network but keeps named volumes.
- `docker compose down -v` deletes database and Redis volumes. This is destructive.
- Back up PostgreSQL regularly and test restoration. Redis cache/rate-limit data can generally be rebuilt, but persistence is enabled in this sample.
- Do not expose PostgreSQL or Redis ports to the host by default.
- Put TLS, authentication, request-size limits, and trusted proxy configuration at a properly configured ingress for public deployment.
- Keep `.env` out of version control and use a secrets manager in production.
- Resource limits are conservative starting points, not universal sizing recommendations. Adjust based on actual memory and workload measurements.

## 8. Local Mac M1 guidance

Start with `WORKER_CONCURRENCY=1`. Keep Ollama on the host and avoid running multiple large models simultaneously. If Docker Desktop memory pressure becomes high, disable Prometheus until needed, reduce worker concurrency, and inspect container memory usage before increasing limits.

## 9. Validation status

Deployment files, monitoring configuration, and the load-test script are committed. They have not been built or run in Docker in this session. Before production use, verify image builds, migration execution on a fresh PostgreSQL volume, restart behavior, backup/restore, Redis availability, and measured load on the target machine.
