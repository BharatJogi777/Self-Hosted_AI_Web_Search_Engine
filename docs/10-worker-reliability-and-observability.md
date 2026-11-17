# 10 — Production Worker Reliability and Observability

This module hardens the PostgreSQL queue worker introduced in Module 9. The goal is not exactly-once execution: distributed workers can crash at inconvenient moments. The practical goal is **at-least-once execution with idempotent effects**, bounded concurrency, recoverable leases, and enough telemetry to diagnose failures.

## 1. Lease renewal

A job claim records `locked_by` and `locked_until`. A fixed lease alone is unsafe for work whose duration is unpredictable. The worker now renews its lease periodically, at approximately one third of the configured lease duration.

Renewal succeeds only when:
- the job is still in the running state;
- the exact worker-slot ownership token still matches;
- the existing lease has not expired.

Each claimed job receives a unique owner token, even when several worker slots belong to the same process. This prevents one slot from accidentally completing another slot's claim.

If renewal fails, the worker marks its local lease as lost and refuses to mark the job completed or failed. It does not forcibly stop an in-flight HTTP request; the result may still be persisted. This is why the document repository's content-hash-based persistence must remain idempotent.

## 2. At-least-once, not exactly-once

Consider a worker that successfully saves a page and crashes before marking the job completed. After lease expiry, another worker may fetch and save the same page again.

The correct design is:
- make ingestion safe to repeat;
- use stable page identity and content hashes;
- append a new page version only when content changes;
- treat queue completion as a separate transaction from page persistence.

Do not claim exactly-once processing. The database cannot atomically commit a remote HTTP request and a separate queue state transition.

## 3. Configurable worker concurrency

The worker supports these environment variables:

| Variable | Default | Meaning |
|---|---:|---|
| `WORKER_CONCURRENCY` | 2 | Concurrent worker slots in one process |
| `WORKER_LEASE_SECONDS` | 120 | Lease duration; must be at least 6 seconds |
| `WORKER_POLL_SECONDS` | 1 | Delay when no job is available |
| `WORKER_METRICS_PORT` | 9100 | Prometheus scrape port |
| `WORKER_ID` | generated | Process identity |
| `LOG_LEVEL` | INFO | Log verbosity |

Every slot claims jobs independently. The database's `FOR UPDATE SKIP LOCKED` prevents two workers from claiming the same currently available row.

Within one process, a per-domain async lock serializes whole crawl operations for a domain. The fetcher's host rate limiter also spaces requests. These controls are **process-local**; multiple worker processes can still crawl the same domain concurrently. A later module will add a shared PostgreSQL domain scheduler/lease.

## 4. Graceful shutdown

The worker listens for SIGINT and SIGTERM. On shutdown it stops claiming new jobs and allows active jobs to finish before disposing the database engine.

This is a graceful-drain strategy, not an instant kill. Configure container termination grace periods to exceed the maximum expected active job duration. A hard kill still relies on lease expiry and retry.

## 5. Structured JSON logs

Worker logs are emitted as JSON with fields such as:
- timestamp, level, logger, message;
- worker_id and job_id;
- attempt number;
- event name and processing duration;
- exception details when available.

Use the job ID as a correlation key when tracing a job across claim, heartbeat, completion, and retry logs. Avoid logging fetched page bodies, credentials, or sensitive query strings.

Example shape:

```json
{
  "timestamp": "2026-11-18T12:00:00+00:00",
  "level": "INFO",
  "logger": "search.crawl_worker",
  "message": "Crawl job completed",
  "event": "job_completed",
  "worker_id": "crawler-a",
  "job_id": "..."
}
```

## 6. Prometheus metrics

The worker exposes a Prometheus scrape endpoint on `WORKER_METRICS_PORT` (default 9100).

Metrics include:
- `search_crawl_jobs_claimed_total`
- `search_crawl_jobs_completed_total`
- `search_crawl_jobs_failed_total`
- `search_crawl_job_leases_lost_total`
- `search_crawl_active_workers`
- `search_crawl_job_duration_seconds`
- `search_crawl_pending_jobs`
- `search_crawl_running_jobs`

The metrics endpoint is per process. If several worker processes share a host, assign a distinct metrics port to each process or configure a proper Prometheus multiprocess deployment. Do not expose the metrics port publicly without network controls.

## 7. Run a worker

Install dependencies and apply migrations first:

```bash
pip install -r requirements.txt
alembic upgrade head
```

Configure and start:

```bash
export DATABASE_URL='postgresql+asyncpg://search:search@localhost:5432/search_engine'
export ALLOWED_DOMAINS='example.com,docs.example.org'
export WORKER_CONCURRENCY=2
export WORKER_LEASE_SECONDS=120
export WORKER_METRICS_PORT=9100

python -m app.workers.crawl_worker
```

Scrape metrics locally:

```bash
curl http://127.0.0.1:9100/metrics
```

## 8. Test strategy

The SQLite unit test verifies that lease renewal requires the current owner and an unexpired lease. It does not prove PostgreSQL locking semantics.

Run the normal test suite:

```bash
python -m pytest -q
```

Add PostgreSQL integration tests before production use:
1. two independent sessions claim jobs concurrently and never receive the same active claim;
2. lease renewal extends the expiry for the current owner;
3. an old owner cannot renew or complete after another worker reclaims the job;
4. a worker crash leads to reclaim after lease expiry;
5. shutdown stops new claims while an active job completes;
6. duplicate ingestion does not create duplicate page versions.

## 9. Important limitations

- Domain serialization and request spacing are local to one process, not distributed.
- The worker marks a lease lost but does not cancel an in-flight HTTP request.
- A heartbeat database outage causes the worker to conservatively treat the lease as lost.
- Prometheus metrics are process-local; configure unique ports or multiprocess collection.
- Metrics currently expose counters, queue depth, active slots, and duration; alerting rules and dashboards are not included.
- Authentication, queue quotas, job cancellation, and operational admin endpoints remain future work.
- Application-level public-IP checks do not replace network egress restrictions.

## 10. Exercises

1. Set `WORKER_LEASE_SECONDS=30` and observe heartbeat renewals while a job is running.
2. Temporarily block database access during heartbeat and observe the lease-lost log.
3. Run with `WORKER_CONCURRENCY=1`, then 4, and compare throughput and remote-host load.
4. Send SIGTERM during an active crawl and verify the worker drains before exiting.
5. Scrape `/metrics` and explain each counter, gauge, and histogram.
6. Run two processes with different metrics ports and confirm both are independently scrapeable.

## 11. Next module

Next: distributed per-domain scheduling and politeness. We will coordinate crawl delays across worker processes, persist robots policy/cache state, and add sitemap discovery and crawl budgets.
