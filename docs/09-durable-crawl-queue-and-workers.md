# 09 — Durable Crawl Queue and Worker Architecture

## 1. Why a queue?

A synchronous HTTP handler holds a client connection open while it fetches remote pages, waits for robots policy, extracts HTML, and writes to PostgreSQL. Network latency is unpredictable. Long-running work should be accepted quickly and executed independently.

The new flow is:

```text
POST /crawl-jobs
       |
       v
Validate URL against configured allowlist
       |
       v
Insert durable crawl_jobs row
       |
       v
Return job_id (202 Accepted)
       |
       v
Independent worker claims job
       |
       v
robots -> fetch -> extract -> persist
       |
       +---- success ---> completed
       |
       +---- error ----> retry with backoff or failed
```

## 2. Why PostgreSQL first?

A controlled corpus can begin with PostgreSQL as both document store and queue. It avoids operating another service and provides transactions, indexes, and row-level locking. This is not automatically the best queue for every workload. At high job volume, complex routing, or strict throughput requirements, evaluate a dedicated broker.

## 3. Job state machine

| State | Meaning |
|---|---|
| pending | Waiting until available_at |
| running | Claimed by a worker with a lease |
| completed | Crawl and persistence succeeded |
| failed | Maximum attempts exhausted |

A failed job can be manually re-enqueued later. An expired running lease makes the job eligible for another worker to claim.

## 4. Atomic claiming with SKIP LOCKED

Workers must not select the same pending job. PostgreSQL's `FOR UPDATE SKIP LOCKED` lets concurrent workers lock different candidate rows without waiting on each other. The claim operation updates the job to running, increments attempts, records worker identity, and sets a lease expiry in one transaction.

A lease is not a permanent lock. If a process dies, another worker can reclaim the job after `locked_until`. The lease must exceed the expected operation duration or be extended by a heartbeat. This first version uses a 120-second lease and does not yet heartbeat; long crawls may therefore be reclaimed prematurely. Add heartbeat/lease renewal before increasing crawl timeouts.

## 5. Retries and exponential backoff

Failures are rescheduled with a bounded exponential delay:

```text
delay = min(300 seconds, 2 ^ attempts)
```

Attempts are incremented when a worker claims a job. Once attempts reach max_attempts, the job becomes failed. Store a bounded error message for diagnosis; avoid persisting secrets or full response bodies.

## 6. Duplicate submission

A partial unique index permits only one pending or running job for a URL. This prevents two active jobs for the same URL even if concurrent API requests race. Completed and failed jobs do not block future recrawls.

The repository performs a friendly pre-check, while the database index is the final concurrency guard. The API catches a concurrent unique-index conflict and looks up the already-active job. This is still a first version; verify this behavior under PostgreSQL concurrency tests.

## 7. Run the worker

After applying migrations, configure the database and crawl scope:

```bash
export DATABASE_URL='postgresql+asyncpg://search:search@localhost:5432/search_engine'
export ALLOWED_DOMAINS='example.com,docs.example.org'

python -m app.workers.crawl_worker
```

Run multiple worker processes in separate terminals or containers. They coordinate through PostgreSQL row locks. Do not run multiple processes with different allowlists against the same queue unless that behavior is intentional.

## 8. Submit and inspect jobs

```bash
curl -X POST http://127.0.0.1:8000/crawl-jobs \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com/","max_attempts":5}'

curl http://127.0.0.1:8000/crawl-jobs/JOB_UUID
```

The endpoint validates the URL before enqueueing and checks the configured domain allowlist. The worker independently enforces URL policy and safe DNS resolution before making network requests.

## 9. Operational and security gaps to close

- Add authentication and authorization to crawl submission and job inspection.
- Add lease heartbeat/renewal for long-running fetches.
- Catch active-job unique conflicts and return the existing job.
- Add a maximum queue depth and per-domain pending-job limits.
- Add job cancellation and administrative retry endpoints.
- Add metrics for queue age, retries, failures, and processing duration.
- Use distributed per-host rate limiting across worker processes; the current fetcher's limiter is process-local.
- Add PostgreSQL integration tests for SKIP LOCKED, partial unique indexes, lease recovery, and concurrent claims.
- Consider a dead-letter policy and retention/cleanup for completed jobs.
- Restrict worker network egress at infrastructure level as well as in application code.

## 10. Exercises

1. Start two worker processes and enqueue ten distinct URLs. Confirm jobs are not simultaneously claimed twice.
2. Kill a worker after it claims a job. Observe lease expiry and recovery.
3. Force a fetch error and observe retry delay and attempts.
4. Submit the same URL twice while pending and verify only one active job exists.
5. Inspect the queue using SQL and explain each state.
6. Add a heartbeat method and test lease extension.

## 11. Next module

Next we will harden the worker lifecycle with lease renewal, concurrency limits, per-host scheduling, observability, and PostgreSQL integration tests. Only after this foundation is reliable should we introduce a separate broker.
