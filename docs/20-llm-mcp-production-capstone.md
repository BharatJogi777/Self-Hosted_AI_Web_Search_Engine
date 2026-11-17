# Module 20 — LLM Integration, MCP, and Production Capstone

## 1. What this module builds

The search engine now exposes two integration surfaces:

1. **Grounded answer API** — `POST /ask` uses Ollama chat tool calling. The model decides when to invoke `search_web`; the application executes the search against the existing reranked hybrid search pipeline, passes bounded results back to the model, and returns an answer with a source list.
2. **MCP server** — `app.mcp.server` exposes `search_web` and `get_document` as Model Context Protocol tools for compatible MCP clients.

The LLM does not crawl the public web itself. It searches the corpus your crawler has already collected and indexed. Search quality, coverage, and freshness therefore depend on your crawl scope and indexing status.

## 2. Grounded answer flow

```text
User question
  -> POST /ask
  -> Ollama /api/chat with search_web tool schema
  -> model requests search_web(query, limit)
  -> application runs query understanding + hybrid retrieval + reranking
  -> bounded result snippets and source URLs returned to model
  -> model writes answer using [1], [2] citations
  -> API returns answer and structured sources
```

The service caps tool rounds with `LLM_MAX_TOOL_ROUNDS` (default 3), caps each search to eight results, truncates snippets before sending them to the model, and treats retrieved page content as untrusted data. The source list is assembled by the application, not invented by the model.

## 3. Ollama configuration

Pull a chat model that supports tool calling. The default configuration uses:

```bash
ollama pull qwen3:4b
ollama pull nomic-embed-text
ollama list
```

The embedding model and chat model have different jobs:

- `nomic-embed-text` converts document chunks and queries into vectors.
- `qwen3:4b` interprets the question, chooses whether to call search, and writes the final response.

Environment:

```bash
OLLAMA_BASE_URL=http://host.docker.internal:11434
EMBEDDING_MODEL=nomic-embed-text
LLM_MODEL=qwen3:4b
LLM_TIMEOUT_SECONDS=120
LLM_MAX_TOOL_ROUNDS=3
```

The chat model must support Ollama's `/api/chat` tool-calling format. If you choose another model, verify tool calling with a small direct Ollama request first.

## 4. Run the grounded API

Start the stack as described in Module 19, and ensure Ollama is running on the host:

```bash
docker compose up --build -d
```

Ask a question:

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"How does PostgreSQL full-text search rank documents?"}'
```

Example response shape:

```json
{
  "question": "How does PostgreSQL full-text search rank documents?",
  "answer": "PostgreSQL can rank matching documents using ts_rank_cd [1].",
  "sources": [
    {
      "id": "1",
      "url": "https://www.postgresql.org/docs/current/textsearch-controls.html",
      "title": "Controlling Text Search"
    }
  ],
  "tool_calls": 1
}
```

The example is illustrative; actual results depend on the indexed corpus. The endpoint is rate limited and does not cache generated answers.

## 5. MCP server

Install the project dependencies in your Python environment:

```bash
python -m pip install -r requirements.txt
```

With the API running, start the MCP server:

```bash
export SEARCH_API_BASE_URL=http://localhost:8000
python -m app.mcp.server
```

The server uses stdio transport. Configure your MCP-compatible client to launch this command from the repository directory and pass `SEARCH_API_BASE_URL` in its environment.

Available tools:

- `search_web(query, limit=5)` — runs the reranked search endpoint and returns titles, URLs, snippets and scores.
- `get_document(document_id)` — returns metadata for a stored document.

For a client launched inside the same Docker network, set `SEARCH_API_BASE_URL=http://api:8000`. For a client on the host, use `http://localhost:8000`.

The MCP process is a tool adapter, not a second crawler or search index. It delegates to the API so URL policy, retrieval and ranking remain centralized.

## 6. Security and grounding rules

- Retrieved web content is untrusted. It may contain prompt injection attempts; do not treat it as instructions.
- Keep tool schemas narrow and validate arguments in application code.
- Bound tool-call rounds, result count, snippet length, timeouts and model output.
- Do not expose crawl administration tools to an untrusted model or anonymous MCP client.
- Keep MCP stdio credentials and environment configuration private.
- The current MCP tools are read-only. Crawling and indexing remain protected API operations and are not exposed as MCP tools.
- Citations are source references, not proof that every generated statement is correct. Evaluate factual support and citation precision.

## 7. Production architecture and responsibilities

| Component | Responsibility |
|---|---|
| FastAPI | Public API, validation, rate limiting |
| Crawl worker | Durable crawl jobs, retries, politeness |
| PostgreSQL + pgvector | Page versions, FTS, vector index |
| Redis | Shared rate limits and short-lived search cache |
| Ollama embeddings | Vector representation |
| Ollama chat | Tool selection and answer generation |
| MCP server | Standard tool interface for external agents |
| Prometheus | Worker metrics |

Keep the LLM decision layer separate from the execution layer: the model chooses a tool and arguments; deterministic Python services validate and execute the action. This is easier to test, observe, and secure than allowing model output to directly perform arbitrary network requests.

## 8. Evaluation checklist

Before calling the capstone production-ready, test:

- [ ] A question that has relevant indexed evidence.
- [ ] A question with no relevant evidence; the model should say it cannot find enough support.
- [ ] A page containing prompt-injection text; the model must treat it as data.
- [ ] Ollama unavailable or model not pulled; API returns a controlled error.
- [ ] Tool call with invalid arguments; no arbitrary tool execution.
- [ ] Multiple search tool calls stop at the configured maximum.
- [ ] Citations map to real URLs returned by search.
- [ ] MCP client can list and invoke both tools.
- [ ] Rate limits apply to `/ask`.
- [ ] Search quality changes are measured with the Module 16 evaluation harness.

## 9. Project completion and known limitations

The 20-module learning sequence is now represented in the repository. This is a substantial learning implementation, not a verified commercial search service. The code and tests have been committed, but the full suite, migrations, Docker image, Ollama tool-calling flow, MCP handshake, and end-to-end capstone have not been executed in this session.

Remaining engineering work before production use includes live PostgreSQL/pgvector integration testing, Docker build and restore testing, model-specific tool-call validation, prompt-injection evaluation, authentication/authorization for external clients, API observability, and representative relevance/load benchmarks.
