# 07 — PostgreSQL Full-Text Search

## 1. Why not SQL LIKE?

A query such as `WHERE extracted_text ILIKE '%database%'` scans text and treats search as substring matching. It does not provide language-aware normalization, relevance ranking, or an index designed for text retrieval. PostgreSQL full-text search provides those capabilities without an external search cluster.

## 2. The core data types

- **Lexeme:** a normalized word form produced by PostgreSQL's text search configuration.
- **tsvector:** the document representation containing lexemes and their positions.
- **tsquery:** the parsed representation of the user's query.
- **GIN:** an inverted index that maps lexemes to rows containing them.

For example, English stemming can normalize related word forms so a search for a term may match documents containing a related grammatical form. Stop words and stemming depend on the selected language configuration.

## 3. Convert document text to a searchable vector

Migration 0002 adds a generated column:

```sql
ALTER TABLE page_versions
ADD COLUMN search_vector TSVECTOR
GENERATED ALWAYS AS (
  to_tsvector('english', coalesce(extracted_text, ''))
) STORED;

CREATE INDEX ix_page_versions_search_vector
ON page_versions USING GIN (search_vector);
```

Because the column is generated, PostgreSQL recalculates it when extracted_text changes. Page versions are immutable in the application, so each stored revision gets its own search vector. The GIN index accelerates the match operator.

## 4. Parse user queries

`websearch_to_tsquery('english', user_input)` accepts familiar search syntax, including quoted phrases, OR, and minus-prefixed exclusions. It is generally more forgiving for a public search box than expecting users to learn PostgreSQL's native tsquery grammar.

The query text is passed as a bound parameter. Never concatenate user input into SQL. Parameterization protects the SQL statement; it does not decide whether a query is useful or cheap, so still enforce query length, timeout, rate limits, and result limits at the API boundary.

## 5. Match and rank

The key predicate is:

```sql
search_vector @@ websearch_to_tsquery('english', :query)
```

The `@@` operator checks whether the vector matches the query. `ts_rank_cd` calculates a relevance score using cover density. It is a baseline ranking signal, not a complete web ranking algorithm. Later we can combine text relevance with freshness, domain quality, link signals, and semantic similarity.

`ts_headline` produces a short excerpt with matching terms highlighted. Treat its output as untrusted HTML if you later render it in a browser; escape or sanitize it before inserting it into a page.

## 6. Search only the current page version

A page may have many historical versions. Searching all of them would return duplicate results and stale content. The repository joins pages to page_versions and requires:

```sql
page_versions.content_hash = pages.current_content_hash
```

This ensures only the version whose hash is currently recorded on the page is eligible for results. A changed document becomes searchable as soon as its new version is committed.

## 7. Run the migration

With PostgreSQL configured through DATABASE_URL:

```bash
alembic upgrade head
python -m pytest -q
```

The query-construction tests compile SQL using PostgreSQL's dialect; they do not execute PostgreSQL operators. A real PostgreSQL integration test is still required before production deployment. SQLite cannot validate tsvector, websearch_to_tsquery, ts_rank_cd, ts_headline, or GIN behavior.

## 8. Query plan and operations

Use `EXPLAIN (ANALYZE, BUFFERS)` with representative data to confirm that PostgreSQL uses the GIN index. Tiny tables may correctly use a sequential scan. Keep statistics current with ANALYZE/autovacuum, monitor query latency, and consider statement timeouts for expensive queries.

For large corpora, evaluate pagination carefully. Offset pagination becomes increasingly expensive at high offsets; a later API can use cursor/keyset pagination based on score plus a stable tie-breaker.

## 9. Exercises

1. Compare `ILIKE '%search%'` with a tsvector match on a realistic dataset.
2. Explain why the GIN index is on page_versions rather than pages.
3. Change a page's content and verify that the previous version no longer appears in normal search results.
4. Try quoted phrases, OR, and minus exclusions with websearch_to_tsquery.
5. Run EXPLAIN ANALYZE and explain when a sequential scan is reasonable.

## 10. Next module

Next we will connect the crawler, extractor, repository, and search components into a controlled ingestion workflow and expose a search API with validation, pagination, and error handling.
