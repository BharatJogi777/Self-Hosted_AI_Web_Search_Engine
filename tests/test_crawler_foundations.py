import pytest

from app.crawler.frontier import CrawlFrontier
from app.crawler.robots import RobotsPolicy
from app.crawler.url_policy import URLPolicy, URLRejected


@pytest.fixture
def policy() -> URLPolicy:
    return URLPolicy(allowed_domains={"example.com"})


def test_accepts_allowed_domain_and_subdomain(policy: URLPolicy) -> None:
    assert policy.normalize("https://example.com") == "https://example.com/"
    assert (
        policy.normalize("https://docs.example.com/guide")
        == "https://docs.example.com/guide"
    )


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/file",
        "https://notexample.com/",
        "https://example.com.attacker.test/",
        "https://user:password@example.com/",
        "http://localhost/",
        "http://api.localhost/",
        "http://127.0.0.1/",
        "http://[::1]/",
        "https://example.com:8443/",
        "https:///missing-host",
    ],
)
def test_rejects_unsafe_or_out_of_scope_urls(
    policy: URLPolicy, url: str
) -> None:
    with pytest.raises(URLRejected):
        policy.normalize(url)


def test_normalizes_scheme_host_default_port_and_fragment(
    policy: URLPolicy,
) -> None:
    assert (
        policy.normalize("HTTPS://DOCS.EXAMPLE.COM:443/guide#install")
        == "https://docs.example.com/guide"
    )
    assert (
        policy.normalize("http://example.com:80/path?q=1#section")
        == "http://example.com/path?q=1"
    )


def test_preserves_query_parameters(policy: URLPolicy) -> None:
    assert (
        policy.normalize("https://example.com/search?q=python&page=2")
        == "https://example.com/search?q=python&page=2"
    )


def test_frontier_deduplicates_and_returns_fifo(policy: URLPolicy) -> None:
    frontier = CrawlFrontier(policy, max_pages=5, max_depth=2)

    assert frontier.add("https://example.com/", depth=0, parent_url=None)
    assert not frontier.add(
        "https://EXAMPLE.com/#top", depth=0, parent_url=None
    )
    assert frontier.add(
        "https://example.com/docs", depth=1, parent_url="https://example.com/"
    )

    first = frontier.pop()
    second = frontier.pop()

    assert first is not None and first.url == "https://example.com/"
    assert second is not None and second.url == "https://example.com/docs"
    assert second.parent_url == "https://example.com/"
    assert frontier.pop() is None


def test_frontier_enforces_depth_and_page_limit(policy: URLPolicy) -> None:
    frontier = CrawlFrontier(policy, max_pages=1, max_depth=1)

    assert not frontier.add("https://example.com/deep", depth=2, parent_url=None)
    assert frontier.scheduled_count == 0

    assert frontier.add("https://example.com/", depth=0, parent_url=None)
    assert not frontier.add(
        "https://example.com/another", depth=1, parent_url=None
    )
    assert frontier.scheduled_count == 1


def test_frontier_rejects_out_of_scope_discovered_link(
    policy: URLPolicy,
) -> None:
    frontier = CrawlFrontier(policy)
    with pytest.raises(URLRejected):
        frontier.add("https://outside.test/", depth=1, parent_url=None)


def test_robots_policy_allows_and_disallows_paths() -> None:
    rules = """
User-agent: *
Disallow: /private/
Allow: /private/public.html
"""
    policy = RobotsPolicy(
        robots_url="https://example.com/robots.txt",
        user_agent="SelfHostedSearchBot",
        robots_text=rules,
    )

    assert policy.can_fetch("https://example.com/index.html")
    assert not policy.can_fetch("https://example.com/private/secret.html")
    assert policy.can_fetch("https://example.com/private/public.html")
    assert not policy.can_fetch("https://other.example.com/index.html")
