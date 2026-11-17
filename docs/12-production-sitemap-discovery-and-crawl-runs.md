# 12. Production sitemap discovery and distributed crawl runs

## 1. Why a crawl run is different from a crawl job

A crawl job is one URL to fetch. A crawl run is the complete bounded operation started from one seed URL. A run owns:
- one seed URL;
- a maximum number of unique discovered URLs;
- a maximum link depth;
- the jobs created from the seed and its discovered links;
- an aggregate status and job counts.

This separation lets multiple worker processes expand one crawl without relying on local counters.

## 2. Database model

Migration `0006_crawl_runs` creates `crawl_runs` and adds `run_id`, `depth`, and `parent_url` to `crawl_jobs`.

`crawl_runs.discovered_count` is a reservation count, not a success count. The seed reserves slot one. Each newly inserted child job reserves one additional slot in the same transaction. The repository locks the run row before checking and incrementing the count. If the URL is duplicate or insertion violates a uniqueness constraint, the transaction rolls back and the slot is not consumed.

The unique constraint on `(run_id, url)` prevents duplicate discoveries within a run. The existing partial unique index on active job URLs prevents two active jobs for the same normalized URL across runs.

## 3. Depth semantics

- Seed URL: depth 0.
- Links and sitemap page URLs discovered from the seed: depth 1.
- Links discovered from depth-1 pages: depth 2.
- A child is accepted only when `depth <= max_depth`.

The API bounds `max_depth` to 0–10 and `max_pages` to 1–5000. The page budget counts unique URL reservations, including the seed, rather than successful downloads. Failed jobs still consumed a discovery slot; this prevents a failing site from creating an unbounded queue.

## 4. Sitemap discovery

The worker starts sitemap discovery after successfully crawling the seed. It requests `/sitemap.xml`, parses either a `urlset` or `sitemapindex`, and follows nested sitemap indexes with:
- a maximum of five sitemap documents;
- a maximum of 500 discovered page URLs;
- cycle detection;
- URLPolicy validation;
- exact same-host restriction.

Sitemap fetches use SafeHTTPFetcher, including the configured response-size limit, DNS public-address checks, redirect validation, and timeout. XML content types are explicitly allowed by the fetcher.

The parser uses Python's standard XML parser and does not fetch URLs itself. The discovery service authorizes every returned location before it can enter the queue.

## 5. Page-link discovery

During normal HTML ingestion, anchors are extracted from the already-fetched response. Links are resolved relative to the final URL, normalized by URLPolicy, restricted to the exact current hostname, and capped at 1,000 per page. The worker submits them at `current_depth + 1`. PostgreSQL enforces the run's maximum depth and page budget.

This is a same-host crawler by design. Cross-host links are not followed even if another host happens to be in ALLOWED_DOMAINS. Start a separate run for another host.

## 6. API

Create a run:

```http
POST /crawl-runs
Content-Type: application/json

{
  "url": "https://docs.example.com/",
  "max_pages": 200,
  "max_depth": 2,
  "max_attempts": 5
}
```

The response contains `run_id` and `seed_job_id`. Poll its status:

```http
GET /crawl-runs/{run_id}
```

The status response includes `discovered_count` and counts by job state. A run becomes completed when it has no pending or running jobs. Completed means processing is terminal; individual jobs may have failed.

## 7. Apply and verify

```bash
alembic upgrade head
pytest -q
```

The queue's atomic row-locking behavior and the existing partial-index concurrency behavior must be exercised against PostgreSQL with competing worker sessions. SQLite unit tests cover basic model and budget behavior but do not prove PostgreSQL concurrency semantics.

## 8. Current boundaries

- Sitemap discovery currently starts at `/sitemap.xml`. The `Sitemap:` directive inside robots.txt is not yet used.
- Sitemap URLs and page links are restricted to the seed hostname.
- No JavaScript rendering, browser automation, sitemap gzip support, or RSS/Atom discovery.
- A run's `discovered_count` measures reserved unique jobs, not pages successfully stored.
- Run cancellation, per-run authentication/quotas, and resumable operator controls are future work.
- Robots cache persistence columns exist from the previous module, but the ingestion path still fetches robots.txt per page; persistent cache wiring is separate work.

Always respect robots.txt, site terms, crawl-delay directives where supported, and explicit site restrictions. Never bypass authentication, paywalls, CAPTCHAs, or access controls.
