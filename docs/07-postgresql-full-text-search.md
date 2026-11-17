# 07 — PostgreSQL Full-Text Search

## 1. Why not SQL LIKE?

A query such as `WHERE extracted_text ILIKE '%database%'` scans text and treats search as substring matching. It does not provide language-aware normalization, relevance ranking, or an index designed for text retrieval. PostgreSQL full-text search provides those capabilities without an external search cluster.

## 2. The core data types

- **Lexeme:** a normalized word form produced by PostgreSQL's text search configuration.
- **tsvector:** the document representation containing lexemes and their positions.
- **tsquery:** the parsed representation of the user's query.
- **GIN:** an inverted index that maps lexemes to rows containing them.

English stemming can normalize related word forms. Stop words and stemming depend on the selected language configuration. This module starts with English; multilingual search needs language detection and a per-language indexing strategy.

## 3. Build a weighted document vector

Migration 0002 adds a basic generated tsvector over extracted text. Migration 0003 extends it with a title snapshot and weighted title/body vector:

```sql
setweight(to_tsvector('english', coalesce(title_snapshot, '')), 'A')
||
setweight(to_tsvector('english', coalesce(extracted_text, '')), 'B')
```

A title match receives weight A and body text receives weight B. A is more important than B during ranking. The title is copied into each immutable page version, so later page-title changes do not rewrite historical snapshots.

The generated column is stored by PostgreSQL and recomputed when its source columns change. The migration creates a GIN index on this vector.

## 4. Parse user queries

`websearch_to_tsquery('english', user_input)` accepts familiar search syntax, including quoted phrases, OR, and minus-prefixed exclusions. It is more forgiving for a public search box than requiring users to learn PostgreSQL's native tsquery grammar.

The query is passed as a bound parameter. Never concatenate user input into SQL. Parameterization protects the SQL statement; it does not decide whether a query is useful or cheap. Enforce query length, timeouts, rate limits, and result limits at the API boundary.

## 5. Match, rank, and build snippets

The core match predicate is:

```sql
search_vector @@ websearch_to_tsquery('english', :query)
```

The `@@` operator checks whether the vector matches the query. `ts_rank_cd` calculates a relevance score using cover density. It is a baseline ranking signal, not a complete web ranking algorithm.

`ts_headline` produces an excerpt with matching terms highlighted. Treat its output as untrusted HTML if you render it in a browser; escape or sanitize it before inserting it into a page.

## 6. Search only the current page version

A page can have many historical versions. Searching all versions would return duplicate and stale results. The repository joins pages to page_versions and requires:

```sql
page_versions.content_hash = pages.current_content_hash
```

Only the currently indexed content revision is eligible for normal search results. Historical versions remain stored for auditing and future features.

## 7. Run migrations

With PostgreSQL configured through DATABASE_URL:

```bash
export DATABASE_URL='postgresql+asyncpg://search:search@localhost:5432/search_engine'
alembic upgrade head
python -m pytest -q
```

Migrations 0002 and 0003 are PostgreSQL-specific. The SQL-construction tests verify query shape but do not execute PostgreSQL operators. A real PostgreSQL integration test is still required before production deployment. SQLite cannot validate tsvector, websearch_to_tsquery, ts_rank_cd, ts_headline, generated columns, or GIN behavior.

## 8. Use the repository

```python
from app.database.session import create_session_factory
from app.search.postgres_search import PostgresSearchRepository

sessions = create_session_factory()
search = PostgresSearchRepository(sessions)

results = await search.search(
    'distributed systems -"beginner tutorial"',
    limit=10,
    offset=0,
    domain="example.com",
)
```

The repository validates non-empty queries, limits from 1 to 100, and non-negative offsets. It uses bound SQL parameters and fixes the text-search configuration to English rather than accepting arbitrary SQL fragments.

## 9. Query plans and operations

Use `EXPLAIN (ANALYZE, BUFFERS)` with representative data to confirm whether PostgreSQL uses the GIN index. Tiny tables may correctly use a sequential scan. Keep statistics current, monitor query latency, and consider statement timeouts for expensive queries.

Offset pagination becomes increasingly expensive at high offsets. Add cursor/search-after pagination for large result sets, using rank plus a stable tie-breaker.

## 10. Exercises

1. Compare `ILIKE '%search%'` with a tsvector match on realistic data.
2. Explain why the GIN index is on page_versions rather than pages.
3. Change a page's content and verify the old version no longer appears in normal results.
4. Try quoted phrases, OR, and minus exclusions with websearch_to_tsquery.
5. Run EXPLAIN ANALYZE and explain when a sequential scan is reasonable.
6. Change title weight from A to B and compare ranking.

## 11. Next module

Next we will connect crawling, extraction, persistence, and search behind a controlled ingestion workflow and expose the search functionality through FastAPI with validation, pagination, and error handling.
