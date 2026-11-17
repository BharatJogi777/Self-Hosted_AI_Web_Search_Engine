# 04 — Safe Asynchronous HTTP Fetcher

## 1. Responsibility

The fetcher takes one URL already discovered by the crawler and returns a bounded HTML response. It does not discover links, extract article text, or index content.

Its responsibilities are:

- Revalidate the URL against crawler scope.
- Resolve DNS and reject unsafe destination addresses.
- Use validated DNS answers for the actual connection.
- Disable automatic redirects and validate each redirect target.
- Apply timeouts and response-size limits.
- Accept only supported content types.
- Retry selected transient failures.
- Apply a per-host minimum request interval.
- Return structured metadata rather than an unstructured string.

## 2. Why aiohttp and a custom resolver?

The project uses aiohttp for asynchronous HTTP requests. Its connector accepts a custom DNS resolver.

`PublicOnlyResolver` resolves a hostname, checks every returned IP address, and gives aiohttp only globally routable addresses. The HTTP request still uses the original hostname, preserving the Host header and TLS hostname verification.

DNS caching is disabled in the connector so each new connection performs a fresh resolution check. Redirects are not followed automatically; the fetcher processes each redirect itself and sends the destination through URLPolicy again.

This is stronger than resolving a hostname separately and then allowing a second, unrelated DNS lookup at connection time.

Network egress controls are still recommended in production. Run the crawler in a restricted network environment that cannot reach internal services or cloud metadata endpoints.

## 3. SSRF protection layers

Server-Side Request Forgery (SSRF) occurs when an application can be tricked into making requests to destinations the caller should not control.

The fetcher uses several layers:

1. URLPolicy permits only configured domains and HTTP(S).
2. URLPolicy rejects IP-literal hosts, credentials, localhost names, and nonstandard ports.
3. PublicOnlyResolver rejects non-global DNS answers.
4. aiohttp connects using the validated resolver results.
5. Automatic redirects are disabled.
6. Every redirect URL is resolved relative to the previous URL and validated again.
7. `trust_env=False` prevents environment proxy configuration from silently changing the network path.

Do not expose arbitrary crawl URLs to unauthenticated users. Add outbound firewall rules as defense in depth.

## 4. Download limits

A malicious or accidental response can consume memory and worker capacity.

The fetcher:
- Rejects a declared Content-Length larger than the configured limit.
- Counts bytes while streaming, even when Content-Length is absent or incorrect.
- Uses a total request timeout.
- Accepts only HTML and XHTML in this first version.
- Enables decompression but applies the size check to the decompressed stream.

The size limit is a byte limit, not a character limit. HTML decoding and content extraction happen in a later module.

## 5. Redirects

Redirects can point to a different host, scheme, or path. Never assume a redirect is safe because the original URL was safe.

This implementation:
- Disables automatic redirect following.
- Supports relative and absolute Location values.
- Revalidates the new URL against the same allowlist.
- Stops after a configurable maximum redirect count.

A redirect to an unrelated host is rejected by URLPolicy.

## 6. Retries and politeness

The fetcher retries network failures and selected transient statuses (429, 500, 502, 503, 504) a bounded number of times.

It understands Retry-After as seconds or an HTTP date, but caps the wait to a configured maximum. Production policy may choose to pause the host for longer rather than cap the server's requested delay; the important point is to avoid retry storms.

HostRateLimiter enforces a minimum interval between requests to the same hostname within one process. It is not a distributed rate limiter. If multiple worker processes are running, move host scheduling and rate limits into shared storage.

## 7. Install and run tests

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pytest -q
```

Tests cover IP classification, DNS rejection, bounded streaming, Retry-After parsing, and configuration validation.

## 8. Example

```python
import asyncio

from app.crawler.fetcher import SafeHTTPFetcher
from app.crawler.url_policy import URLPolicy


async def main() -> None:
    policy = URLPolicy(allowed_domains={"www.python.org"})
    fetcher = SafeHTTPFetcher(
        policy,
        user_agent="ExampleResearchCrawler/0.1 (+https://your-domain.example/bot)",
        timeout_seconds=12,
        max_response_bytes=1_000_000,
        max_redirects=4,
        max_retries=2,
        min_host_interval_seconds=1.5,
    )

    page = await fetcher.fetch("https://www.python.org/")
    print("Final URL:", page.final_url)
    print("Status:", page.status)
    print("Content type:", page.content_type)
    print("Downloaded bytes:", len(page.body))


if __name__ == "__main__":
    asyncio.run(main())
```

Replace the example user-agent contact URL with a real project policy/contact page before running a public crawler. Ensure the target site permits your crawling and that robots.txt allows the selected user-agent and path.

## 9. Current limitations

This is a foundation, not a complete distributed crawling platform:

- Rate limiting is process-local.
- There is no persistent retry queue yet.
- There is no distributed concurrency control.
- The fetcher does not itself fetch or evaluate robots.txt; the crawl orchestration layer must check RobotsPolicy before calling fetch.
- There is no browser rendering for JavaScript-heavy pages.
- There is no sitemap parser yet.
- There is no crawl-job authentication/API yet.

The fetcher also needs integration tests against a controlled local test server. The unit tests intentionally avoid making requests to public websites.

## 10. Completion checklist

- [ ] Dependencies install in a clean Python 3.12 virtual environment.
- [ ] Unit tests pass.
- [ ] Unsafe DNS answers are rejected.
- [ ] Redirects are revalidated.
- [ ] Oversized response bodies are rejected.
- [ ] Only supported HTML content types are accepted.
- [ ] Timeouts and retry limits are configured.
- [ ] Robots policy is checked by orchestration before fetching.

Next: content extraction — turn raw HTML into clean, searchable page text while preserving title, canonical URL, metadata, and provenance.
