# Module 18 — Production API Security, Caching, and Rate Limiting

## 1. Security boundaries

The API now distinguishes read/search traffic from operations that mutate the crawl corpus or consume significant resources.

The following routes require an API key in the `X-API-Key` header:

- `POST /crawl`
- `POST /crawl-jobs`
- `POST /crawl-runs`
- `GET /crawl-jobs/{job_id}`
- `GET /crawl-runs/{run_id}`
- `POST /documents/{document_id}/index`

Configure one or more comma-separated keys with `API_KEYS`. Keys are trimmed and compared with `hmac.compare_digest`. Do not commit keys, put them in URLs, or log request headers. Rotate by temporarily accepting old and new keys, deploy clients with the new key, then remove the old key.

If no keys are configured, protected routes fail closed with HTTP 503 rather than becoming anonymously writable. A missing or invalid key returns HTTP 401.

This is a simple shared-secret mechanism, not a full identity platform. For multi-tenant deployments, use a gateway or identity provider with per-client scopes, revocation, audit trails, and key management.

## 2. Search rate limiting

All `GET /search...` routes are rate limited. Defaults:

- `SEARCH_RATE_LIMIT=60`
- `SEARCH_RATE_WINDOW_SECONDS=60`

The client identity is the direct TCP peer address. The service deliberately does not trust arbitrary `X-Forwarded-For` values. When deployed behind a reverse proxy, configure trusted proxy handling at the ASGI server or gateway and ensure clients cannot bypass that proxy.

Without Redis, the fallback limiter is in-memory and per process. It is suitable only for local development and single-process experiments. It resets on restart and does not coordinate multiple Uvicorn workers or hosts.

When `REDIS_URL` is configured, the limiter uses an atomic Redis Lua script and shared counters. Redis connection or startup failures are not silently downgraded to local mode.

## 3. Search response caching

When Redis is configured, successful GET search responses are cached for a short TTL (default 30 seconds):

- `SEARCH_CACHE_TTL_SECONDS=30`

The cache key includes the exact request path and query string, hashed with SHA-256. The versioned key namespace makes future cache-format changes easier. Responses are not cached without Redis, and non-200 responses are not cached.

This cache is appropriate only while search results are public and identical for all callers. If authorization or tenant-specific visibility is added to search, include the authorization scope/tenant in the cache key or disable shared caching. Never cache private responses under a global key.

The rate limit is checked before the cache lookup, so a hot cached query cannot bypass abuse controls.

## 4. Redis setup

Example local Redis service:

```bash
docker run --rm --name search-redis -p 6379:6379 redis:7-alpine
```

Environment:

```bash
export API_KEYS="replace-with-a-long-random-secret"
export REDIS_URL="redis://localhost:6379/0"
export SEARCH_RATE_LIMIT=60
export SEARCH_RATE_WINDOW_SECONDS=60
export SEARCH_CACHE_TTL_SECONDS=30
```

Install updated dependencies:

```bash
python -m pip install -r requirements.txt
```

Do not expose Redis publicly. Use authentication/TLS and network isolation in production. Keep secrets in a secret manager or deployment environment, not in source control.

## 5. Operational considerations

- Terminate TLS at a trusted ingress or reverse proxy.
- Restrict database and Redis network access.
- Use separate credentials and least-privilege database roles.
- Set request/body limits and connection limits at the ingress.
- Add audit events for administrative actions without recording API keys.
- Add per-key quotas and revocation before exposing a public multi-client API.
- Configure trusted proxy handling carefully; IP-based limits are not user identity.
- Consider CORS only when browser clients need it; CORS is not authentication.
- The current fixed-window limiter can allow a short burst around window boundaries. Token bucket or sliding-window policies may be preferable for stricter fairness.

## 6. Validation

The module adds unit/API tests for key parsing, authentication behavior, and the local rate limiter. Run:

```bash
pytest -q
```

Redis integration, PostgreSQL integration, multi-worker behavior, and load testing must be verified in the deployment environment. These tests have been committed but have not been executed in this development session.
