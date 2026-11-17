# Module 16 — Search Quality Evaluation

## Why evaluation comes before tuning

A search engine can return plausible-looking results while consistently placing the best answer too low. We need a repeatable way to compare ranking changes.

This module introduces a small **judged query set** (also called qrels) and computes standard ranking metrics. The included dataset is synthetic starter data: replace its document IDs and judgments with pages from your own crawl corpus.

## 1. Build a relevance judgment set

For each test query, record documents and a relevance grade:

- 0: not relevant
- 1: partially relevant
- 2: strongly relevant
- 3: highly relevant / directly answers the query

Have a human judge the query-document pair using a written rubric. Ideally, use two independent reviewers for ambiguous queries and resolve disagreements. Do not use the current ranking order to decide relevance.

Keep queries representative:
- Navigational: a known page, product, or API name
- Informational: a concept or explanation
- Troubleshooting: an error or failure symptom
- Exact technical terms: identifiers, methods, configuration keys
- Natural language: intent expressed without exact document wording

Store judgments in `evaluation/queries.json`. Each query has a stable ID, the query text, and a mapping of document IDs to graded relevance.

## 2. Metrics implemented

For a cutoff k:

### Precision@k

Fraction of the top k returned results that are relevant:

`relevant results in top k / k`

This penalizes irrelevant results in the visible result set.

### Recall@k

Fraction of all judged relevant documents found in the top k:

`relevant results in top k / all judged relevant documents`

Recall is useful for measuring whether candidate retrieval misses relevant pages.

### MRR@k

Mean Reciprocal Rank is averaged across queries. For one query, reciprocal rank is `1 / rank of the first relevant result`; it is zero when no relevant result appears in the top k.

MRR rewards getting at least one useful answer near the top.

### MAP@k

Average Precision rewards ranking multiple relevant documents early. The implementation divides the sum of precision at each relevant hit by `min(number of judged relevant documents, k)`, then macro-averages across queries.

### NDCG@k

Normalized Discounted Cumulative Gain supports graded relevance. Higher relevance grades earn larger gain (`2^grade - 1`) and results lower in the list are discounted logarithmically. A perfect ordering has NDCG 1.

All aggregate metrics are macro-averages: each query contributes equally. Queries with no positive relevance judgments produce zero for recall, MRR, MAP and NDCG; avoid including such queries unless that is an intentional test case.

## 3. Run the evaluator

From the repository root:

```bash
python scripts/evaluate_search.py
python scripts/evaluate_search.py --qrels evaluation/queries.json --run evaluation/sample_run.json -k 5
pytest -q tests/test_search_evaluation.py
```

The run file maps each query ID to an ordered list of document IDs:

```json
{
  "results": {
    "q1": ["doc-a", "doc-b", "doc-c"]
  }
}
```

The sample run exists to demonstrate the evaluator; it is not a live measurement of the search engine. Export IDs and ordered results from `/search/hybrid` or `/search/reranked` to evaluate a real corpus.

## 4. Compare retrieval and ranking

For a useful experiment, generate separate run files for:
1. PostgreSQL lexical search
2. Semantic search
3. Hybrid RRF
4. Hybrid plus reranking

Evaluate all runs against exactly the same qrels and cutoff. Record the git commit, configuration, model name, candidate limit, and date alongside every result. Change one variable at a time.

Interpret metrics together:
- Higher recall but lower precision can mean broader candidate retrieval.
- Higher MRR but unchanged recall can mean the first useful result moved upward.
- Higher NDCG means graded relevant results are better ordered.
- A reranker cannot recover a relevant document that candidate retrieval never returned.

## 5. Important limitations

- The starter judgments are synthetic and are not evidence of real search quality.
- Metrics are only as trustworthy as the relevance judgments.
- Unjudged documents are treated as non-relevant by this simple evaluator. For larger corpora, use pooled judgments from several retrieval systems and assess judgment coverage.
- Duplicate result IDs are ignored after their first occurrence.
- This module evaluates offline ranked lists; it does not call PostgreSQL, Ollama, or the API.
- Do not tune weights against a tiny test set and report the result as general performance. Keep a held-out query set for final comparisons.

## Next

Module 17 adds query understanding: normalization, spelling suggestions, synonyms, and query expansion. Evaluation from this module will let us measure whether those changes help or hurt.
