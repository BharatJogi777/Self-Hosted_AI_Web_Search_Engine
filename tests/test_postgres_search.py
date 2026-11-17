from app.search.postgres_search import build_search_statement


def test_search_uses_websearch_to_tsquery_and_gin_vector():
    sql = str(build_search_statement())
    assert "websearch_to_tsquery('english', :query)" in sql
    assert "pv.search_vector @@ user_query.tsq" in sql


def test_search_returns_only_current_page_version():
    sql = str(build_search_statement())
    assert "pv.content_hash = p.current_content_hash" in sql


def test_search_supports_domain_filter_and_pagination():
    sql = str(build_search_statement())
    assert ":domain IS NULL OR p.domain = :domain" in sql
    assert "LIMIT :limit OFFSET :offset" in sql


def test_search_ranks_and_builds_highlighted_snippets():
    sql = str(build_search_statement())
    assert "ts_rank_cd" in sql
    assert "ts_headline" in sql
