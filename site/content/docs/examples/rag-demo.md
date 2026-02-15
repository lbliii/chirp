---
title: RAG Demo
description: Streaming AI Q&A with cited sources — Chirp's flagship example
draft: false
weight: 10
lang: en
type: doc
tags: [examples, rag, sse, streaming, fragments, htmx]
keywords: [rag, sse, streaming, fragments, event delegation, ollama]
category: tutorial
---

## Overview

The RAG (Retrieval Augmented Generation) demo is Chirp's most comprehensive example. It showcases fragments, Server-Sent Events, dual-model streaming, event delegation, and free-threading — all with zero client-side JavaScript frameworks.

**Location:** `examples/rag_demo/`

## What It Demonstrates

| Feature | How |
|--------|-----|
| **Fragments** | `Fragment("ask.html", "answer", ...)` streams HTML blocks via SSE |
| **SSE** | `EventStream` yields fragments; htmx swaps into `sse-swap` targets |
| **Dual streaming** | Compare two models side-by-side; each streams independently (free-threading) |
| **Event delegation** | Copy button and compare toggle use `document.addEventListener` because `hx-on` does not run on SSE-swapped content |
| **chirp.data** | SQLite with typed frozen dataclasses for document storage |
| **chirp.ai** | Streaming LLM via Ollama (default) or Anthropic |
| **referenced routes** | `/share/{slug}` and `/ask/stream` use `referenced=True` so `chirp check` does not flag them as orphan |

## Key Patterns

### SSE Swap Target Structure

- **Outer** `.answer` — `sse-swap="answer"` target with `hx-target="this"`; has padding and border
- **Inner** `.answer-body` — `data-copy-text`; no extra padding (avoids double borders)
- **Content** `.answer-content.prose` — markdown-rendered answer

Use `hx-disinherit="hx-target hx-swap"` on `sse-connect` and `hx-target="this"` on each `sse-swap` element. See [[docs/streaming/sse-patterns|SSE patterns]] for the multi-swap layout.

### Copy Button

Keep `.copy-btn` in normal flow — avoid `position: absolute` in your CSS so each button stays anchored to its answer. In compare mode, each card has its own copy button.

### Event Delegation

`hx-on::click` does not work on content swapped by htmx. The RAG demo uses `AppConfig(delegation=True)`, which injects a document-level listener for `.copy-btn` and `.compare-switch`:

```javascript
document.addEventListener('click', function(e) {
  var copyBtn = e.target.closest('.copy-btn');
  if (copyBtn) {
    var wrap = copyBtn.closest('[data-copy-text]');
    if (wrap) navigator.clipboard.writeText(wrap.dataset.copyText || '');
  }
});
```

### Compare Toggle

A `role="switch"` button toggles `aria-checked` and enables/disables the second model selector. The form's `input[name=compare]` stays in sync for server-side handling.

## Run

```bash
pip install chirp[ai,data]
ollama serve   # Start Ollama first
cd examples/rag_demo && python app.py
```

Open http://127.0.0.1:8000 and ask a question about the docs.

## Chirp Macros

For the standard answer structure (body + prose + copy button), use the ``sse_answer`` macro:

```html
{% from "chirp/sse_answer.html" import sse_answer %}
{{ sse_answer(text, text | markdown | cite(sources) | safe(reason="patitas")) }}
```

The RAG demo uses custom logic for streaming states; the macro suits the final "done" state.

## Next Steps

- [[docs/streaming/sse-patterns|SSE patterns]] — Multi-swap layout, hx-target, compile-time checks
- [[docs/streaming/server-sent-events|Server-Sent Events]] — SSE in depth
- [[docs/templates/fragments|Fragments]] — Block-level rendering
- [[docs/tutorials/htmx-patterns|htmx Patterns]] — Event delegation and more
