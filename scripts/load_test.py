from __future__ import annotations

import argparse
import asyncio
import statistics
import time

import httpx


async def run(args: argparse.Namespace) -> None:
    semaphore = asyncio.Semaphore(args.concurrency)
    latencies: list[float] = []
    statuses: dict[int, int] = {}

    async with httpx.AsyncClient(
        base_url=args.base_url.rstrip("/"),
        timeout=args.timeout,
        limits=httpx.Limits(
            max_connections=args.concurrency,
            max_keepalive_connections=args.concurrency,
        ),
    ) as client:
        async def one_request() -> None:
            async with semaphore:
                started = time.perf_counter()
                try:
                    response = await client.get(
                        args.endpoint,
                        params={"q": args.query, "limit": args.limit},
                    )
                    statuses[response.status_code] = statuses.get(response.status_code, 0) + 1
                except httpx.HTTPError:
                    statuses[0] = statuses.get(0, 0) + 1
                finally:
                    latencies.append(time.perf_counter() - started)

        wall_started = time.perf_counter()
        await asyncio.gather(*(one_request() for _ in range(args.requests)))
        wall_seconds = time.perf_counter() - wall_started

    ordered = sorted(latencies)

    def percentile(value: float) -> float:
        if not ordered:
            return 0.0
        index = min(len(ordered) - 1, int((len(ordered) - 1) * value))
        return ordered[index] * 1000

    print(f"requests: {args.requests}")
    print(f"concurrency: {args.concurrency}")
    print(f"duration_seconds: {wall_seconds:.2f}")
    print(f"throughput_rps: {args.requests / wall_seconds:.2f}")
    print(f"status_counts: {dict(sorted(statuses.items()))}")
    print(f"latency_ms_p50: {statistics.median(ordered) * 1000:.2f}")
    print(f"latency_ms_p95: {percentile(0.95):.2f}")
    print(f"latency_ms_p99: {percentile(0.99):.2f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Small concurrent search API smoke/load test.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--endpoint", default="/search")
    parser.add_argument("--query", default="postgres indexing")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args()
    if args.requests < 1 or args.concurrency < 1 or args.limit < 1:
        parser.error("requests, concurrency, and limit must be positive")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
