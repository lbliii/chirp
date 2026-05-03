---
title: SSE
description: Minimal Server-Sent Events with strings, SSEEvent, and Fragment payloads
draft: false
weight: 50
lang: en
type: doc
tags: [examples, sse, eventstream, realtime]
keywords: [sse, server sent events, eventstream, fragments]
category: examples
---

## What It Teaches

Use this example when updates happen after the page is loaded. `EventStream`
opens a long-lived SSE response and the generator yields values over time:
plain strings, structured `SSEEvent` payloads, or rendered `Fragment(...)`
payloads.

This is intentionally not a Suspense example. Suspense is for initial render;
SSE is for post-load updates.

## Run It

```bash
PYTHONPATH=src python examples/standalone/sse/app.py
```

Open `http://127.0.0.1:8000/`.

## Test It

```bash
pytest examples/standalone/sse/
```

## Contract Surface

SSE examples exercise the per-event boundary: a bad fragment should not casually
kill a stream intended to stay open. They also exercise template block
cross-references between yielded `Fragment(...)` values and htmx `sse-swap`
targets.

## Source

- [`app.py`](https://github.com/lbliii/chirp/blob/main/examples/standalone/sse/app.py)
- [`README.md`](https://github.com/lbliii/chirp/blob/main/examples/standalone/sse/README.md)

## Next

- [[docs/streaming/server-sent-events|Server-Sent Events]]
- [[docs/streaming/sse-patterns|SSE Patterns]]
- [[docs/testing/assertions|Testing Assertions]]
