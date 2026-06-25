---
title: LLM Minimal
description: Smallest streaming-LLM example — TemplateStream and EventStream side by side
draft: false
weight: 45
lang: en
type: doc
tags: [examples, streaming, llm, templatestream, eventstream, sse]
keywords: [llm, templatestream, eventstream, streaming, minimal]
category: examples
---

## Overview

LLM Minimal is the smallest path to streaming tokens in Chirp — two forms on one
page, simulated tokens by default (no Ollama or API keys required). Reach for it
when [[docs/build-apps/streaming-updates/streaming-answers|Streaming answers]]
describes the transport × client matrix and you want a runnable reference.

**Location:** `examples/standalone/llm_minimal/`

:::{note}
Related examples: [[docs/examples/sse|SSE]] (EventStream only),
`chirpui/llm_playground/` (ChirpUI shell variant),
`examples/standalone/llm_streaming_kida/` (Kida templates).
:::

## What it demonstrates

:::{list-table}
:header-rows: 1

* - Form
  - Transport
  - Client wiring
* - First form (full page)
  - `TemplateStream`
  - Plain `<form method="post">` — no `hx-target`
* - Second form (in place)
  - `EventStream`
  - htmx swaps in an SSE panel with parametric `sse-connect`
:::

Chirp's `template_stream_client_shape` contract warns if you htmx-swap a
`TemplateStream` response into a div. See
[[docs/quality/contracts-debugging/categories|Contract categories]] for the
streaming-related checks.

## Run

```bash
PYTHONPATH=src python examples/standalone/llm_minimal/app.py
```

Open http://localhost:8000/ and try both forms.
