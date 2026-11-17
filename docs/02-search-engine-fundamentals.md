# 02 — Search Engine Fundamentals

## 1. The central idea

A search engine does not magically know every web page. It builds and maintains a searchable collection of documents, then uses that collection to answer queries.

The classic pipeline is:

```text
Discover → Crawl → Parse → Extract → Normalize → Store → Index
                                                       ↓
User query → Understand → Retrieve candidates → Rank → Return results
```

These stages are related, but they solve different problems. Keeping them separate makes the system easier to test and scale.

## 2. Crawler vs indexer vs search engine vs search API

### Web crawler
A crawler is a program that requests web pages and discovers links to other pages. It is responsible for controlled acquisition, not relevance ranking.

### Indexer
An indexer transforms fetched content into data structures that make retrieval efficient. For example, it can build an inverted index mapping terms to documents.

### Search engine
A search engine combines an index, query processing, candidate retrieval, ranking, and result presentation.

### Search API
A search API exposes search-engine functionality over HTTP. It is an interface to the engine; it is not itself the crawler or index.

## 3. Crawling

A crawler begins with one or more seed URLs.

Example:

- `https://docs.example.org/`
- `https://docs.example.org/sitemap.xml`

It fetches a page, extracts links, normalizes them, checks policy, and schedules eligible URLs.

Important terms:

- **Seed URL:** starting point for discovery.
- **Frontier:** queue or set of URLs waiting to be fetched.
- **Canonical URL:** preferred URL representing a page.
- **Crawl depth:** number of link hops from a seed.
- **Politeness:** limits that avoid overwhelming a website.
- **Robots.txt:** a site-published set of crawler instructions; it is not authorization to ignore other site terms or access restrictions.

A production crawler needs bounds: allowed hosts, maximum pages, maximum depth, per-host concurrency, request delay, timeouts, maximum response bytes, and redirect limits.

## 4. URL normalization and deduplication

The same content can appear at multiple URLs:

- `https://example.org/article`
- `https://example.org/article/`
- `https://www.example.org/article?utm_source=newsletter`

Normalization can remove known tracking parameters, normalize host casing, and resolve relative links. But normalization must be conservative: query parameters may change the actual content.

Useful deduplication signals:

1. Canonical URL supplied by the page.
2. Normalized URL.
3. Hash of extracted text.
4. Optional near-duplicate detection for very similar content.

Do not assume two different URLs are duplicates just because their paths look similar.

## 5. Extraction

Raw HTML contains navigation, scripts, advertisements, footers, and main content.

The extraction stage tries to retain:
- Page title.
- Main text.
- Description.
- Canonical URL.
- Language when detectable.
- Publication or modification date when reliably available.
- Original fetch URL and fetch timestamp.

Extraction is imperfect. Store provenance and avoid inventing missing metadata.

## 6. Indexing and the inverted index

Suppose our tiny corpus contains:

- D1: "LangChain supports agents and tools."
- D2: "FastAPI builds Python APIs."
- D3: "Agents can call tools."

An inverted index maps each term to the documents containing it:

| Term | Documents |
|---|---|
| langchain | D1 |
| supports | D1 |
| agents | D1, D3 |
| tools | D1, D3 |
| fastapi | D2 |
| python | D2 |
| apis | D2 |
| call | D3 |

Instead of scanning every document for every query, the search engine uses the index to find candidate documents.

Real indexes also store positions, frequencies, field information, and other statistics that support phrase matching and ranking.

## 7. Query processing

A query processor may:
- Trim and validate input.
- Normalize case.
- Tokenize text.
- Remove or retain stop words depending on the query.
- Handle phrases and quoted terms.
- Apply filters such as host, language, or date.
- Expand synonyms or spelling variants in later versions.

Be careful with technical queries. Terms such as `C++`, `ERR_CONNECTION_RESET`, `v1.2.0`, and `foo.bar()` can be damaged by naive tokenization.

## 8. Retrieval vs ranking

These are not the same operation.

**Retrieval** finds a candidate set that may contain relevant documents.

**Ranking** orders those candidates so the most useful results appear first.

For example, a query might retrieve 500 candidates, then a ranking stage returns the best 10.

A system that retrieves relevant pages but ranks them poorly still feels like a bad search engine.

## 9. Lexical retrieval and BM25

Lexical retrieval matches query terms against document terms. BM25 is a widely used ranking function that considers:
- Term frequency in a document.
- How rare a term is across the corpus (inverse document frequency).
- Document length normalization.

Intuition:
- A query term appearing in a document is evidence of relevance.
- A rare term is usually more informative than a common term.
- Repeating a term helps, but with diminishing returns.
- Very long documents should not win simply because they contain more words.

PostgreSQL full-text search provides a practical starting point. Its ranking functions are useful, but should not be described as identical to every BM25 implementation.

## 10. Semantic retrieval

Semantic retrieval represents text as vectors (embeddings). Similar meanings can be close in vector space even when they do not share exact words.

Example:

- Query: "How can an agent execute external functions?"
- Page: "Tool calling lets a model request application-side function execution."

Lexical overlap may be limited, but semantic similarity can be high.

Semantic retrieval introduces new concerns:
- Embedding model selection.
- Chunking strategy.
- Vector dimensions and storage.
- Model version consistency.
- Re-embedding after model changes.
- Similarity metric and threshold calibration.

An embedding score is not a truth score.

## 11. Hybrid retrieval

Hybrid retrieval combines lexical and semantic candidates or scores.

A simple conceptual model is:

`hybrid_score = alpha * lexical_score + (1 - alpha) * semantic_score`

This is only a starting point. Raw scores from different systems may not be calibrated or directly comparable. Reciprocal Rank Fusion (RRF) is another practical approach because it combines rankings rather than assuming scores share the same scale.

For technical documentation, lexical signals are especially important for exact names, symbols, versions, and error messages.

## 12. Ranking signals

Possible ranking features include:
- Lexical relevance.
- Semantic similarity.
- Title match.
- Exact phrase match.
- Domain or source quality.
- Freshness, when recency matters.
- Duplicate suppression.
- Language and user filters.

Do not blindly use popularity or freshness as universal relevance signals. A timeless reference page may be more useful than a new but shallow article.

Start with a transparent baseline, evaluate it, and add features only when they improve measured quality.

## 13. Search result anatomy

A useful result should contain enough information for both people and AI agents:

```json
{
  "page_id": "stable-document-id",
  "title": "Tool calling concepts",
  "url": "https://docs.example.org/tool-calling",
  "snippet": "A short extract relevant to the query...",
  "score": 0.82,
  "retrieval_method": "lexical",
  "fetched_at": "2026-11-18T00:00:00Z"
}
```

The values above are illustrative. A score is an internal ranking signal, not an 82% probability that the page is correct.

For grounded LLM responses, retain the source URL and enough content to verify the generated claims.

## 14. Evaluation: how do we know search is good?

Create a small test set of queries and manually label relevant pages.

Useful metrics:

- **Precision@k:** among the top k results, what fraction are relevant?
- **Recall@k:** among all known relevant pages, what fraction appear in the top k?
- **MRR:** how highly is the first relevant result ranked?
- **nDCG@k:** evaluates ranking when relevance has multiple grades.

Example: if the top 5 results contain 3 relevant pages, Precision@5 is 3/5 = 0.60.

A search engine should be evaluated on a repeatable query set before and after ranking changes.

## 15. Practical exercise

Use a small, permitted corpus of 10–20 technical documentation pages.

For each page, record:
- URL.
- Title.
- Extracted main text.
- Content hash.
- Fetch timestamp.

Then answer these questions:

1. What is the difference between a crawler and an indexer?
2. Why do we build an inverted index?
3. What is the difference between retrieval and ranking?
4. Why can lexical search outperform semantic search for exact error codes?
5. Why is a relevance score not a probability of truth?
6. Why should crawling be a separate background workflow from search requests?

## 16. Completion criteria

You are ready for the next implementation module when you can explain the full pipeline and distinguish discovery, fetching, extraction, indexing, retrieval, and ranking.

## 17. Next module

Next: implement a safe, bounded URL discovery and crawler foundation. We will start with URL validation, host allowlists, robots policy, and a testable frontier before sending network requests.
