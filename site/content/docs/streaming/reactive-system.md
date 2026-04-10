---
title: Reactive System
description: ReactiveBus, DependencyIndex, and reactive_stream — automatic SSE updates from data changes
draft: false
weight: 23
lang: en
type: doc
tags: [reactive, sse, real-time, bus, dependency-index]
keywords: [reactive, ReactiveBus, DependencyIndex, reactive_stream, derived paths, observability, change events]
category: guide
---

## Overview

Chirp's reactive system connects data mutations to SSE-powered UI updates. When data changes, the system figures out which template blocks are affected and pushes re-rendered fragments to connected browsers — automatically.

Three components work together:

| Component | Role |
|-----------|------|
| `ReactiveBus` | Thread-safe pub/sub event bus scoped by key |
| `DependencyIndex` | Maps context paths to the template blocks that depend on them |
| `reactive_stream()` | Glues the bus and index into an `EventStream` return value |

## ReactiveBus

The bus broadcasts `ChangeEvent`s from any thread to async subscribers.

```python
from chirp.pages.reactive import ReactiveBus, ChangeEvent

bus = ReactiveBus()

# Emit from any thread (e.g., a background worker or POST handler)
bus.emit_sync(ChangeEvent(
    scope="doc-42",
    changed_paths=frozenset({"doc.content", "doc.version"}),
    origin="user-7",   # optional: skip notifying the author
))
```

Subscribers are async iterators scoped by key:

```python
async for event in bus.subscribe("doc-42"):
    print(event.changed_paths)
```

Calling `bus.close("doc-42")` signals all subscribers on that scope to stop. `bus.close()` (no args) closes everything.

### Back-Pressure

Each subscriber gets its own `asyncio.Queue`. When a subscriber's queue is full, events are silently dropped — the bus never blocks the emitter.

```python
bus = ReactiveBus(maxsize=64)   # default: 256
```

Monitor back-pressure with the observability counters:

```python
bus.emitted_count      # total events emitted (including dropped)
bus.dropped_count      # events lost to full queues
bus.subscriber_count   # active subscribers across all scopes
```

All counters are `int`s maintained by the bus for observability.

## ChangeEvent

A frozen dataclass emitted after a data mutation:

```python
@dataclass(frozen=True, slots=True)
class ChangeEvent:
    scope: str                       # e.g., a document ID
    changed_paths: frozenset[str]    # e.g., {"doc.content", "doc.version"}
    origin: str | None = None        # who caused this change
```

- **scope** scopes delivery — subscribers only receive events for their scope.
- **changed_paths** tells the `DependencyIndex` which blocks need re-rendering.
- **origin** enables self-suppression: `reactive_stream()` skips events whose origin matches the current connection, so the client that caused the change isn't notified of it.

## DependencyIndex

Built at app startup from kida's static block analysis. Maps context paths (like `"doc.content"`) to the template blocks that display them.

### Registration

Two approaches:

**Manual** — register specific blocks:

```python
from chirp.pages.reactive.index import DependencyIndex

index = DependencyIndex()
index.register_template(env, "doc/{doc_id}/_layout.html",
    block_names=["title", "content", "word_count"],
    dom_id_map={"title": "doc-title", "content": "doc-body"},
)
```

**Auto from SSE swaps** — scan a template for `sse-swap` elements and register only those blocks:

```python
source = env.loader.get_source(env, "page.html")[0]
index.register_from_sse_swaps(env, "page.html", source,
    exclude_blocks={"editor_content"},  # client-managed, don't re-render
)
```

### Derived Paths

Declare computed relationships between context paths. When a source path changes, derived paths are automatically included in the affected set:

```python
index.derive("doc.word_count", from_paths={"doc.content"})
index.derive("doc.summary", from_paths={"doc.content", "doc.title"})
```

Derivations are **transitive**: if A derives from B and B derives from C, changing C invalidates A, B, and C.

The store emits only what actually mutated. Display blocks that depend on computed values update without extra wiring.

### Querying

```python
blocks = index.affected_blocks(frozenset({"doc.content"}))
# Returns: [BlockRef(template_name="page.html", block_name="content"), ...]
```

Prefix matching is built in — changing `"doc"` affects blocks that depend on `"doc.version"`, and vice versa.

### Debugging

```python
index.explain_affected(frozenset({"doc.content"}))
# {
#   "original_paths": {"doc.content"},
#   "expanded_paths": {"doc.content", "doc.word_count", "doc.summary"},
#   "derived_paths": {"doc.word_count", "doc.summary"},
#   "affected_blocks": [{"template": "page.html", "block": "content", "target": "doc-body"}, ...]
# }
```

## reactive_stream()

The one-liner that ties everything together:

```python
from chirp.pages.reactive import reactive_stream

@app.route("/doc/{doc_id}/live")
def live(doc_id: str) -> EventStream:
    return reactive_stream(
        bus,
        scope=doc_id,
        index=dep_index,
        context_builder=lambda: {"doc": store.get(doc_id)},
        origin=session_id,
    )
```

What happens on each `ChangeEvent`:

1. Skip if `origin` matches (self-suppression)
2. Look up affected blocks via `DependencyIndex`
3. Call `context_builder()` for fresh data
4. Yield a `Fragment` per affected block

Error boundary: if `context_builder()` raises, the event is skipped and the stream continues. The next change event retries with fresh data.

## Contract Validation

`chirp check` validates the reactive system at startup:

| Check | Severity | What it catches |
|---|---|---|
| `reactive_block` | ERROR | `BlockRef` references a non-existent template block (typo or renamed block) |
| `reactive_cycle` | WARNING | Derivation graph contains a cycle |

These checks are only active when the app uses `DependencyIndex`.

## Thread Safety

`ReactiveBus` is fully thread-safe — `emit_sync()` is designed to be called from any thread (background workers, sync POST handlers, etc.). The bus uses a single `threading.Lock` protecting the subscriber registry and counters.

`DependencyIndex` is thread-safe after construction (read-only at runtime). Build it during app startup, then share it across all request handlers.

All Lock-protected paths have dedicated concurrency stress tests. See [[docs/about/thread-safety|Thread Safety]] for the full story.

## Next Steps

- [[docs/streaming/sse-patterns|SSE Patterns]] — Four update patterns using the reactive system
- [[docs/streaming/server-sent-events|Server-Sent Events]] — EventStream basics
- [[docs/about/thread-safety|Thread Safety]] — Free-threading guarantees
