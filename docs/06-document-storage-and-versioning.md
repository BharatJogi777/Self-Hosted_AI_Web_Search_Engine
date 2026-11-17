# 06 — Document Storage and Versioning

## 1. Why persistence is a separate stage

The crawler discovers and fetches a URL. The extractor converts HTML into an ExtractedDocument. The storage layer makes that result durable. Fetching should not contain SQL, and SQL models should not parse HTML.

Pipeline:

```text
URL frontier -> safe fetcher -> HTML extractor -> PageRepository -> PostgreSQL
                                                   |                  |
                                                   |                  +-- pages
                                                   +--------------------- page_versions
```

## 2. Page identity versus page content

A URL identifies a page record; extracted content changes over time. The pages table stores stable URL identity and latest metadata. page_versions stores immutable extracted-text snapshots.

- normalized_url is unique and must come from the crawler URL policy.
- current_content_hash is SHA-256 of normalized extracted text.
- page_versions.version_number increases when extracted text changes.
- A recrawl with the same hash refreshes crawl metadata but creates no new version.

Do not use a page title as identity: titles can change and different pages can share a title. Do not use the canonical URL as crawl permission; canonical metadata is only a hint about duplicate content.

## 3. Why store hashes?

Hashing lets the system compare content cheaply without comparing large text values. Identical normalized text produces the same hash; changed text normally produces a different hash. A hash is a change detector, not proof that two documents are semantically equivalent.

## 4. Repository pattern

PageRepository is the persistence boundary. The crawler calls save_extracted_document(document, normalized_url); it does not construct ORM models. This keeps database changes isolated and makes the repository testable with SQLite.

The transaction updates page metadata and inserts a version together. If an insert fails, the metadata update rolls back too. Unique constraints provide database-level protection against duplicate URL identities and duplicate version numbers.

## 5. Install and test

Create and activate a Python 3.12 virtual environment, then run:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
```

The repository tests use in-memory SQLite, so PostgreSQL is not required to run them. SQLite validates repository behavior; it does not replace PostgreSQL integration testing.

## 6. Configure PostgreSQL and migrate

Set an async SQLAlchemy URL:

```bash
export DATABASE_URL='postgresql+asyncpg://search:search@localhost:5432/search_engine'
alembic upgrade head
```

Use a dedicated database role with only the privileges the application needs. Keep credentials out of source control. In deployment, run migrations as a controlled release step rather than letting every API worker mutate the schema at startup.

To roll back the initial migration:

```bash
alembic downgrade base
```

## 7. Important production limitation: concurrent recrawls

This first repository implementation is appropriate for a single writer per normalized URL. Two workers can race: both may read the same current hash and calculate the same next version number. Unique constraints prevent silent corruption, but one transaction may fail. Before running multiple crawler workers, serialize writes per URL (for example with PostgreSQL advisory locks) or implement an atomic upsert/version allocation strategy and retry conflicts.

Consider retention policies, compressed content storage, content-size limits, deletion workflows, and audit metadata before operating at scale. Raw HTML is deliberately not stored in this first version.

## 8. Exercises

1. Save the same extracted document three times. How many page rows and page-version rows should exist?
2. Change only the title. Should this create a new content version? Explain why.
3. Change the extracted body. What should happen to the version number and hash?
4. Design a safe multi-worker strategy for two workers recrawling the same URL concurrently.
5. Explain why a canonical URL must not bypass the crawler domain allowlist.

## 9. What comes next

Next we will expose a small ingestion workflow and API boundaries, then add PostgreSQL full-text indexing. Semantic embeddings and pgvector come after a reliable document lifecycle.
