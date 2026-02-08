# RAG Demo — Streaming AI Answers, Zero JavaScript

A documentation site with AI-powered Q&A. Ask a question, get streaming
answers with cited sources. The entire app is ~50 lines of Python.

## What it demonstrates

- **chirp.data** — SQLite database with typed frozen dataclasses
- **chirp.ai** — Streaming LLM responses via Anthropic's Claude
- **EventStream + Fragment** — Server-rendered HTML pushed via SSE
- **htmx** — Browser swaps fragments into the DOM, no JS framework
- **Per-worker lifecycle** — `@app.on_worker_startup` / `@app.on_worker_shutdown` for DB connections
- **Multi-worker Pounce** — 4 worker threads with free-threading

## Architecture

```
Browser (htmx SSE)
    ↓ POST /ask
Chirp handler
    ↓ db.fetch(Document, ...) — retrieve relevant docs from SQLite
    ↓ llm.stream(prompt) — stream Claude's answer with docs as context
    ↓ yield Fragment("ask.html", "answer", text=accumulated)
SSE event: fragment
    ↓ htmx swaps #answer div with re-rendered block
Browser shows streaming text
```

## Lifecycle (multi-worker)

```
Startup (once):
    on_startup → temp DB connect → CREATE TABLE, seed data → disconnect

Per worker (×4):
    on_worker_startup  → Database(URL), connect, store in ContextVar
    serve requests     → _db_var.get() — each worker uses its own connection
    on_worker_shutdown → disconnect, clear ContextVar
```

The split matters because `aiosqlite` binds internal asyncio primitives to
the event loop where the connection was created. Each pounce worker runs
its own event loop in a separate thread, so database connections must be
created per-worker. Schema migration and seeding only need to happen once,
so those stay in `on_startup`.

## Run

```bash
# Set your API key
export ANTHROPIC_API_KEY="sk-..."

# Install dependencies
pip install chirp[ai,data]

# Run (single worker — dev mode)
python examples/rag_demo/app.py

# Run (multi-worker — install pounce first)
pip install pounce
python examples/rag_demo/app.py
```

Open http://127.0.0.1:8000 and ask a question.

## Zero JavaScript

The entire client-side behavior is two HTML attributes:

```html
<form hx-post="/ask" hx-ext="sse" sse-connect="/ask" sse-swap="fragment">
```

- `hx-post="/ask"` — POST the form to /ask
- `sse-connect="/ask"` — connect to the SSE endpoint
- `sse-swap="fragment"` — swap incoming fragments into the DOM

No React. No npm. No webpack. No build step. Just HTML attributes.
