# 11. Distributed crawling and politeness

## Why process-local throttling is insufficient

The HTTP fetcher's rate limiter and the worker's per-domain lock only coordinate tasks inside one Python process. If three worker processes run, each can independently send requests to the same host. A crawler needs a shared coordination point.

This module introduces the `crawl_domains` PostgreSQL table. A domain row contains:
- `next_allowed_at`: earliest time another crawl may begin.
- `lease_owner` and `lease_until`: short-lived ownership for one worker.
- robots.txt body, status, fetch time, and expiry fields for a persistent cache.

## Shared domain leases

`CrawlDomainRepository.try_acquire` uses a PostgreSQL insert-on-conflict followed by a conditional update. Only one worker can acquire a currently available domain row. The lease expires automatically if a process dies. A worker must release the lease when its crawl ends; release schedules the next permitted request time.

This is a coarse domain-level lock: it intentionally serializes one full page crawl per domain. It is conservative, easy to reason about, and safer than multiplying per-process concurrency.

## Robots cache data model

The schema stores robots content and a 24-hour default cache expiry. Cache retrieval and persistence primitives are provided. The ingestion path still uses its existing safe robots fetch and parser in this iteration; wiring cache refresh, HTTP status semantics (404 vs 4xx/5xx), and stale-cache policy is a follow-up hardening task. Until then, do not interpret the presence of these columns as proof that caching is active.

## Sitemap parser

`app.crawler.sitemap.parse_sitemap` parses sitemap `urlset` and `sitemapindex` XML and enforces an entry limit. It does not fetch sitemap URLs. Every returned location must be passed through URLPolicy, and each sitemap fetch must use SafeHTTPFetcher with a strict response-size cap. Sitemap indexes should be traversed with an independent maximum sitemap count and cycle detection.

## Crawl budgets and scope

The in-memory CrawlFrontier already enforces page and depth bounds for a single process. It is not a durable distributed frontier. Durable per-run budgets require a crawl-run record and an atomic page-slot reservation shared by workers; do not use a process-local counter for a production crawl. That distributed run model is intentionally separated from this domain-coordination change.

## Migration and tests

Apply migration `0005_crawl_domains` after the prior migrations:

```bash
alembic upgrade head
```

The sitemap parser tests are local unit tests. Domain lease operations use PostgreSQL-specific upsert semantics and must be tested against PostgreSQL with competing sessions before production use.

## Operational guidance

- Start with one active crawl per domain and a minimum interval of at least one second.
- Use a descriptive crawler User-Agent and publish contact/policy information.
- Respect site terms, robots rules, rate limits, and explicit exclusions.
- Do not bypass authentication, paywalls, CAPTCHAs, or access controls.
- Restrict network egress in addition to application-level URL/DNS checks.
- Monitor lease contention and expired leases; a domain lease is coordination, not a substitute for job leases.
