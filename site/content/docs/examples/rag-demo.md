---
title: RAG Demo
description: Streaming AI Q&A with cited sources — Chirp's broadest single example
draft: false
weight: 10
lang: en
type: doc
tags: [examples, rag, sse, streaming, fragments, htmx]
keywords: [rag, sse, streaming, fragments, ollama, ai, citations]
category: examples
---

## Overview

The RAG demo is a documentation Q&A app: you type a question, it retrieves the
relevant docs from SQLite, and it streams an AI answer with cited sources back
over the wire — no React, no npm, around 50 lines of Python. Reach for it to see
[[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]],
[[docs/build-apps/html-fragments/fragments|fragments]], and free-threaded
dual-model streaming working together in one runnable app.

**Location:** `examples/chirpui/rag_demo/`

:::{note}
This is the broadest single example in the docs. It pulls in `chirp.ai` (LLM
streaming) and `chirp.data` (typed SQLite) on top of the SSE and fragment
machinery. If you only need one feature, start with the smaller
[[docs/examples/sse|SSE example]] first.
:::

## What It Demonstrates

Each row is a feature the demo exercises and the page that owns it:

:::{list-table}
:header-rows: 1

* - Feature
  - In the demo
  - Learn more
* - **Fragments**
  - `Fragment("ask.html", "answer", ...)` renders one named block per token.
  - [[docs/build-apps/html-fragments/fragments|Fragments]]
* - **Server-Sent Events**
  - `EventStream` yields fragments; htmx swaps them into `sse-swap` targets.
  - [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]]
* - **Multi-swap SSE layout**
  - Sources, answer, and share link are separate `sse-swap` targets in one stream.
  - [[docs/build-apps/streaming-updates/sse-patterns|SSE patterns]]
* - **Dual streaming**
  - Compare two models side by side; each streams independently across worker threads.
  - [[docs/about/thread-safety|Free-threading and thread safety]]
* - **Typed SQLite**
  - `chirp.data.Database` returns frozen dataclasses for document storage.
  - [[docs/build-apps/forms-data/database|Database]]
* - **Event delegation**
  - `AppConfig(delegation=True)` wires copy and compare controls on SSE-swapped content.
  - [[docs/tutorials/htmx-patterns|htmx patterns]]
:::

## Run It

Running the demo is an ordered procedure with one prerequisite the model needs —
a local Ollama model — before the app can answer anything.

::::{steps}

:::{step} Install Chirp with the AI extras
The demo stores docs in SQLite, which `chirp.data` serves through the stdlib
`sqlite3` module — no database extra is needed.

```bash
pip install chirp[ai,sessions,markdown]
```
:::{/step}

:::{step} Pull the default Ollama model
The demo uses Ollama by default, so it needs no API key.

```bash
ollama pull llama3.2
```
:::{/step}

:::{step} Start Ollama in another terminal
```bash
ollama serve
```
:::{/step}

:::{step} Run the app
```bash
PYTHONPATH=src python examples/chirpui/rag_demo/app.py
```

It starts four worker threads when `pounce` is installed, and falls back to a
single-worker dev server otherwise.
:::{/step}

:::{step} Open the browser
Open `http://127.0.0.1:8000` and ask a question about the docs.
:::{/step}

::::{/steps}

To use a cloud model instead, set `CHIRP_LLM` (for example
`CHIRP_LLM=anthropic:claude-sonnet-4-20250514`) and the matching API key such as
`ANTHROPIC_API_KEY`.

*Source: [`examples/chirpui/rag_demo/app.py`](https://github.com/lbliii/chirp/blob/main/examples/chirpui/rag_demo/app.py).*

## The Streaming Endpoint

The SSE handler retrieves docs, builds a prompt, and streams the answer
token-by-token. `stream_with_sources` re-renders the named blocks as the model
emits text and yields one `Fragment` per chunk:

```python
from chirp import EventStream, Request, SSEEvent
from chirp.ai.streaming import stream_with_sources


@app.route("/ask/stream", referenced=True, template="ask.html")
async def ask_stream(request: Request) -> EventStream:
    async def generate():
        question = (request.query.get("question") or "").strip()
        sources = await _retrieve_docs(_db_var.get(), question)
        async for frag in stream_with_sources(
            llm.stream(prompt),
            "ask.html",
            sources_block="sources",
            sources=sources,
            response_block="answer",
        ):
            yield frag
        yield SSEEvent(event="done", data="complete")

    return EventStream(generate())
```

This is an excerpt — `prompt`, `_retrieve_docs`, and the per-worker `_db_var` are
defined in the full app. `/ask/stream` and `/share/{slug}` are marked
`referenced=True` so the
[[docs/quality/contracts-debugging/route-contract|route contract]] does not flag
them as orphans — htmx connects to them rather than a browser navigating directly.

## Chirp Macros

Chirp ships a reusable answer macro so you don't hand-write the body, prose, and
copy-button structure for the streamed answer:

:::{tip} Reuse the `sse_answer` macro
Import `sse_answer` from `chirp/sse_answer.html` for the standard answer
structure. It renders the `.answer-body` wrapper (with `data-copy-text`), the
`.answer-content.prose` content, and a `.copy-btn`.

```html
{% from "chirp/sse_answer.html" import sse_answer %}
{{ sse_answer(text, text | markdown | cite(sources) | safe(reason="patitas")) }}
```

`cite` is an app-local filter defined in this demo (`@app.template_filter("cite")`)
that turns `[1]`, `[2]` references into links — it does not ship with Chirp. The
macro suits the final answer; the RAG demo uses its own block for the in-progress
streaming states.
:::

:::{dropdown} How the swap targets and buttons are wired
These are template-internal details specific to this demo. You don't need them to
run it — open this if you're reading `ask.html`.

**Multi-swap structure.** Each answer card opens one SSE connection with
`sse-connect` and `hx-disinherit="hx-target hx-swap"`, then carries three inner
`sse-swap` targets (`sources`, `answer`, `share_link`), each with
`hx-target="this"`. The streamed `.answer-body` uses the `chirpui-streaming-block`
classes for the typing cursor. See
[[docs/build-apps/streaming-updates/sse-patterns|SSE patterns]] for the multi-swap
layout in general.

**Copy and compare controls.** `hx-on::click` is bound at parse time, so it does
not fire on content that htmx swaps in over SSE. The demo sets
`AppConfig(delegation=True)`, which injects one document-level listener that
matches `.copy-btn` and
`.chirpui-copy-btn` for clipboard copy and `.compare-switch` for the
`role="switch"` model toggle. You write the buttons; Chirp wires the behavior. See
[[docs/tutorials/htmx-patterns|htmx patterns]] for event delegation.
:::{/dropdown}

## Next Steps

- [[docs/build-apps/streaming-updates/sse-patterns|SSE patterns]] — multi-swap layout and `hx-target`
- [[docs/examples/sse|SSE example]] — the smaller, single-feature version
- [[docs/build-apps/forms-data/database|Database]] — typed SQLite queries

:::{related}
:::
