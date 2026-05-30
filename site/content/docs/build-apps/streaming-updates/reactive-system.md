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

## ConnectionInfo

Subscriber identity is optional, but it unlocks audience filtering and
presence:

```python
from chirp.pages.reactive import ConnectionInfo

connection = ConnectionInfo(session_id=session_id, user_id=current_user.id)
```

`session_id` is required. `user_id` can be `None` for anonymous viewers.
`connected_at` is captured with `time.monotonic()` when the dataclass is
created. Anonymous connections still count for presence, but audience-filtered
events are delivered only to connections whose `user_id` is in the event's
audience set.

## ChangeEvent

A frozen dataclass emitted after a data mutation:

```python
@dataclass(frozen=True, slots=True)
class ChangeEvent:
    scope: str                       # e.g., a document ID
    changed_paths: frozenset[str]    # e.g., {"doc.content", "doc.version"}
    origin: str | None = None        # who caused this change
    audience: frozenset[str] | None = None
```

- **scope** scopes delivery — subscribers only receive events for their scope.
- **changed_paths** tells the `DependencyIndex` which blocks need re-rendering.
- **origin** enables self-suppression: `reactive_stream()` skips events whose origin matches the current connection, so the client that caused the change isn't notified of it.
- **audience** narrows delivery to subscribers whose `ConnectionInfo.user_id`
  is present in the set. `None` broadcasts to every subscriber in the scope.

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

deps = index.block_dependencies("page.html", "content")
# Returns the context paths that can cause that block to re-render.
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
from chirp.pages.reactive import ConnectionInfo, reactive_stream

@app.route("/doc/{doc_id}/live")
def live(doc_id: str) -> EventStream:
    return reactive_stream(
        bus,
        scope=doc_id,
        index=dep_index,
        context_builder=lambda paths: build_doc_context(doc_id, paths),
        origin=session_id,
        connection=ConnectionInfo(session_id=session_id, user_id=current_user.id),
        on_disconnect=lambda scope, connection: audit_disconnect(scope, connection),
    )
```

What happens on each `ChangeEvent`:

1. Skip if `origin` matches (self-suppression)
2. Deliver only to matching `connection.user_id` when `audience` is set
3. Look up affected blocks via `DependencyIndex`
4. Call `context_builder(changed_paths)` for fresh data when the builder
   accepts one argument; zero-argument builders still work for older apps
5. Yield a `Fragment` per affected block

Use the one-argument form when a page has expensive context assembly. The
argument is the exact `frozenset[str]` from the change event after
`DependencyIndex` expansion has selected affected blocks:

```python
def build_doc_context(changed_paths: frozenset[str]) -> dict:
    if "doc.comments" in changed_paths:
        return {"comments": store.load_comments()}
    return {"doc": store.load_doc()}
```

Error boundary: if `context_builder()` raises, the event is skipped and the stream continues. The next change event retries with fresh data.

### Presence

Connection-aware streams are visible through the bus:

```python
viewers = bus.presence("doc-42")
viewer_count = len(viewers)
```

Presence only includes subscribers that passed `ConnectionInfo`. Use
`on_disconnect` for cleanup or to emit a presence-only change event after a tab
closes.

### Audience Filtering

Use `audience` when a change is relevant to only some connected users:

```python
bus.emit_sync(ChangeEvent(
    scope="doc-42",
    changed_paths=frozenset({"notifications"}),
    audience=frozenset({"alice", "bob"}),
))
```

Subscribers without `ConnectionInfo`, or with a `user_id` outside the audience,
do not receive that event. Broadcast events keep `audience=None`.

## Contract Validation

`chirp check` validates the reactive system at startup:

| Check | Severity | What it catches |
|---|---|---|
| `reactive_block` | ERROR | `BlockRef` references a non-existent template block (typo or renamed block) |
| `reactive_cycle` | WARNING | Derivation graph contains a cycle |
| `reactive_paths` | WARNING | Declared emitted paths are not registered in the dependency index |
| `reactive_audience` | WARNING | Audience-filtered scopes have no connection-aware streams |

These checks are only active when the app uses `DependencyIndex` or declares
reactive metadata:

```python
app.set_contract_check_data("reactive_index", index)
app.set_contract_check_data("reactive_emitted_paths", {"tasks", "presence"})
app.set_contract_check_data("reactive_connection_scopes", {"board"})

# Add this only when the app emits ChangeEvent(..., audience=...).
app.set_contract_check_data("reactive_audience_scopes", {"board"})
```

Register `reactive_index` once at startup, before the app freezes. Keep
`reactive_emitted_paths` in sync with every `ChangeEvent.changed_paths` value
your stores emit. `reactive_connection_scopes` should name scopes whose
`reactive_stream()` call passes `ConnectionInfo`; if a scope also appears in
`reactive_audience_scopes`, `app.check()` can warn when audience-filtered
events would have no connection identity to match.

## Thread Safety

`ReactiveBus` is fully thread-safe — `emit_sync()` is designed to be called from any thread (background workers, sync POST handlers, etc.). The bus uses a single `threading.Lock` protecting the subscriber registry and counters.

`DependencyIndex` is thread-safe after construction (read-only at runtime). Build it during app startup, then share it across all request handlers.

All Lock-protected paths have dedicated concurrency stress tests. See [[docs/about/thread-safety|Thread Safety]] for the full story.

## Next Steps

- [[docs/build-apps/streaming-updates/sse-patterns|SSE Patterns]] — Four update patterns using the reactive system
- [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]] — EventStream basics
- [[docs/about/thread-safety|Thread Safety]] — Free-threading guarantees
