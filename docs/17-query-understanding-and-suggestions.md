# Module 17 — Query Understanding and Search Suggestions

## 1. Where query understanding belongs

The search request pipeline becomes:

```text
User query
  -> normalize whitespace
  -> conservative spelling correction
  -> optional controlled synonym expansion
  -> lexical + semantic candidate retrieval
  -> RRF fusion
  -> reranking
  -> response with original and processed query
```

Query processing must happen before retrieval. It must not mutate stored documents or silently rewrite user intent.

## 2. Normalization

The baseline collapses repeated whitespace. It preserves the original query for diagnostics and does not globally lowercase or strip punctuation from the search string. Terms such as `C++`, `C#`, `v1.2`, and technical identifiers should not be casually rewritten.

## 3. Dictionary-based spelling correction

The starter implementation uses Python's standard-library `difflib.get_close_matches` against an explicit vocabulary. It only considers alphabetic tokens of at least five characters. Unknown tokens remain unchanged.

This is intentionally conservative. Edit-distance similarity is not semantic understanding. For a production corpus, build a vocabulary from document titles, important terms, and query logs, then review it. Avoid auto-correcting product names, API symbols, versions, IDs, or acronyms without strong evidence.

## 4. Controlled synonym expansion

Synonyms are configured explicitly. The baseline has a small example map; it is not a general thesaurus. Expansions are bounded and deduplicated.

Expansion can improve recall while harming precision. Evaluate it against the same judged queries from Module 16. Keep it disabled or restrict it by domain if it makes results worse.

## 5. Suggestions

The `/search/suggestions` endpoint proposes alternatives for the final token using the same vocabulary. Suggestions are not applied automatically. A UI can display them as "Did you mean?" choices.

This is not autocomplete based on query popularity. Popularity-aware suggestions require query logs, privacy controls, aggregation, abuse filtering, and a separate storage design.

## 6. API

- `GET /search/reranked?q=postgres%20conection%20pool` processes the query before hybrid retrieval and reranking. The response includes original, normalized, corrected, and expanded query values.
- `GET /search/suggestions?q=conection` returns bounded spelling suggestions.

Configuration is initially code-based through `default_query_processor()`. Later, corpus-derived vocabulary and synonyms should be loaded from versioned configuration or database tables.

## 7. Evaluation

Create separate run files for:
1. raw query
2. normalized query
3. corrected query
4. corrected plus synonym-expanded query

Use Module 16's qrels and metrics. Compare Recall@k, Precision@k, MRR@k, MAP@k, and NDCG@k. Never assume a query rewrite improves quality simply because it looks more natural.

## 8. Limitations

- Dictionary correction is not a language model and has no contextual spelling awareness.
- The starter vocabulary is deliberately small.
- Synonym expansion is literal and may change query intent.
- No query-log analytics, popularity ranking, or personalization is implemented.
- The query processor is synchronous and lightweight; do not add a network call to this hot path without measuring latency.
