"""Prometheus metrics for crawl worker processes."""
from prometheus_client import Counter, Gauge, Histogram

JOBS_CLAIMED = Counter("search_crawl_jobs_claimed_total", "Crawl jobs claimed")
JOBS_COMPLETED = Counter("search_crawl_jobs_completed_total", "Crawl jobs completed")
JOBS_FAILED = Counter("search_crawl_jobs_failed_total", "Crawl job processing failures")
LEASE_LOST = Counter("search_crawl_job_leases_lost_total", "Crawl job leases lost")
ACTIVE_WORKERS = Gauge("search_crawl_active_workers", "Worker slots currently processing jobs")
JOB_DURATION = Histogram(
    "search_crawl_job_duration_seconds",
    "Time spent processing a crawl job",
    buckets=(1, 5, 10, 30, 60, 120, 300, 600),
)

PENDING_JOBS = Gauge("search_crawl_pending_jobs", "Jobs currently pending")
RUNNING_JOBS = Gauge("search_crawl_running_jobs", "Jobs currently running")
