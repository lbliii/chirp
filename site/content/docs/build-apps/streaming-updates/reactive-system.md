---
title: Reactive System
description: Push fresh HTML to every viewer the moment your data changes — no polling, no manual fan-out
draft: false
weight: 23
lang: en
type: doc
tags: [reactive, sse, real-time, bus, dependency-index]
keywords: [reactive, ReactiveBus, DependencyIndex, reactive_stream, derived paths, change events, presence, audience]
category: guide
---

## Overview

The reactive system pushes fresh HTML to connected browsers the moment your data changes — no client polling, no manual fan-out. You emit a change event after a mutation. Chirp figures out which template blocks display the data that changed and re-renders only those, streaming them over [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]] to every viewer of that resource.

Reach for it when many users watch the same live thing — a shared document, a kanban board, a price ticker — and a server-side change should appear for all of them at once.

:::{note}
Need just **one value** to fan out to every binding on a page? Use a [[docs/build-apps/streaming-updates/signals|signal]] — it is the lighter primitive. Need a **one-way event channel** with no data-to-block mapping? Return an [[docs/build-apps/streaming-updates/server-sent-events|EventStream]] directly. The reactive system is the layer above both: it maps *what changed* to *which blocks re-render*.
:::

Three pieces work together. You will touch all three in the example below.

:::{list-table}
:header-rows: 1

* - Piece
  - What it does
* - `ReactiveBus`
  - A thread-safe pub/sub channel. You emit `ChangeEvent`s on it from any thread; subscribers receive them per scope.
* - `DependencyIndex`
  - Maps context paths (like `"tasks"`) to the template blocks that display them. Built once at startup.
* - `reactive_stream()`
  - Subscribes a route to the bus, runs each change through the index, and returns an `EventStream` of re-rendered fragments.
:::

## Minimal working example

The shortest end-to-end loop: register blocks against context paths, return a `reactive_stream()` from an SSE route, and emit a `ChangeEvent` after each mutation. Open the page in two tabs — change a task in one, watch the other update within a second.

:::{example} Reactive task board (the full loop)
```python
from chirp import App, AppConfig, Fragment, Request
from chirp.pages.reactive import (
    BlockRef, ChangeEvent, ConnectionInfo, DependencyIndex, ReactiveBus, reactive_stream,
)

app = App(config=AppConfig(template_dir="templates", worker_mode="async"))
store = ...  # your thread-safe task store (see the full example below)
bus = ReactiveBus()

# 1. Map the "tasks" context path to every block that displays it.
dep_index = DependencyIndex()
for block in ("task_list", "task_count"):
    dep_index.register("tasks", BlockRef(template_name="board.html", block_name=block))


# 2. Emit a change event after every mutation.
@app.route("/tasks/{task_id:int}/toggle", methods=["POST"])
def toggle(task_id: int):
    store.toggle(task_id)
    bus.emit_sync(ChangeEvent(scope="board", changed_paths=frozenset({"tasks"})))
    return Fragment("board.html", "task_list", tasks=store.all())  # the caller's own tab


# 3. Return reactive_stream() from the SSE route — it does the lookup-and-render.
@app.route("/events", referenced=True)
def events(request: Request):
    session_id = request.headers.get("x-session-id", "anon")
    return reactive_stream(
        bus,
        scope="board",
        index=dep_index,
        context_builder=lambda paths: {"tasks": store.all()},
        connection=ConnectionInfo(session_id=session_id),
    )
```
:::

The full runnable app lives at [`examples/standalone/reactive_tasks`](https://github.com/lbliii/chirp/tree/main/examples/standalone/reactive_tasks).

:::{note} See also

For the four concrete recipes built on this loop — broadcast updates, self-suppression, presence, and audience-filtered notifications — see [[docs/build-apps/streaming-updates/sse-patterns|SSE Patterns]]. This page covers the mechanism; that page covers the recipes.
:::

## Emitting changes

A `ChangeEvent` is a frozen dataclass you emit after a mutation. Four fields:

```python
@dataclass(frozen=True, slots=True)
class ChangeEvent:
    scope: str                          # e.g. a document or board ID
    changed_paths: frozenset[str]       # e.g. {"doc.content", "doc.version"}
    origin: str | None = None           # who caused this change
    audience: frozenset[str] | None = None
```

- **`scope`** routes delivery. Subscribers receive only events for their scope.
- **`changed_paths`** tells the `DependencyIndex` which blocks need re-rendering.
- **`origin`** enables self-suppression: `reactive_stream()` skips events whose `origin` matches the current connection, so the client that caused a change is not re-notified of it.
- **`audience`** narrows delivery to subscribers whose `ConnectionInfo.user_id` is in the set. `None` broadcasts to everyone in the scope.

Emit from any thread — a background worker, a sync POST handler, anywhere:

```python
from chirp.pages.reactive import ChangeEvent

bus.emit_sync(ChangeEvent(
    scope="doc-42",
    changed_paths=frozenset({"doc.content", "doc.version"}),
    origin="user-7",   # skip notifying the author of their own edit
))
```

Emit only what actually mutated. Blocks that display *computed* values stay in sync automatically — see [Derived paths](#derived-paths) below.

## Mapping paths to blocks

The `DependencyIndex` answers one question: *given these changed paths, which template blocks re-render?* The common case needs nothing manual — register a template and kida's static block analysis extracts each block's dependencies for you:

```python
from chirp.pages.reactive import DependencyIndex

index = DependencyIndex()
index.register_template(env, "board.html")
```

For finer control, register a single block against a path by hand:

```python
from chirp.pages.reactive import BlockRef

index.register("tasks", BlockRef("board.html", "task_list"))
index.register("tasks", BlockRef("board.html", "task_count", dom_id="count"))
```

Prefix matching is built in: changing `"doc"` affects blocks that depend on `"doc.version"`, and changing `"doc.version"` affects blocks that depend on `"doc"`.

### Derived paths

Declare computed relationships so a single source change fans out to everything downstream. When a source path changes, derived paths join the affected set automatically — your mutation code only emits what it actually touched:

```python
index.derive("doc.word_count", from_paths={"doc.content"})
index.derive("doc.summary", from_paths={"doc.content", "doc.title"})
```

Derivations are **transitive**: if `A` derives from `B` and `B` derives from `C`, changing `C` expands to `{C, B, A}`. A `word_count` block re-renders when `doc.content` changes, with no extra wiring at the emit site.

## Tracking who's connected

Pass a `ConnectionInfo` when you build the stream to unlock presence and audience filtering. Without it, a connection is anonymous — it still receives broadcast events, but it is invisible to presence and skipped by audience-filtered events.

```python
from chirp.middleware.auth import get_user
from chirp.pages.reactive import ConnectionInfo

user = get_user()  # AnonymousUser when not signed in
connection = ConnectionInfo(
    session_id=session_id,
    user_id=user.id or None,  # "" for anonymous → None
)
```

`session_id` is required; `user_id` is `None` for anonymous viewers; `connected_at` is captured with `time.monotonic()` at construction.

Read presence off the bus by scope:

```python
viewers = bus.presence("doc-42")
viewer_count = len(viewers)
```

`presence()` returns only the connections that supplied a `ConnectionInfo`. Use `on_disconnect` (below) to emit a presence-only change event when a tab closes.

## How `reactive_stream()` runs

`reactive_stream()` is the one call that ties the bus, the index, and the connection together into an `EventStream` you return from a route:

```python
from chirp import EventStream
from chirp.middleware.auth import get_user
from chirp.middleware.sessions import get_session
from chirp.pages.reactive import ConnectionInfo, reactive_stream

@app.route("/doc/{doc_id}/live", referenced=True)
def live(doc_id: str) -> EventStream:
    session_id = get_session()["sid"]
    user = get_user()  # AnonymousUser when not signed in
    return reactive_stream(
        bus,
        scope=doc_id,
        index=dep_index,
        context_builder=lambda paths: build_doc_context(doc_id, paths),
        origin=session_id,
        connection=ConnectionInfo(session_id=session_id, user_id=user.id or None),
        on_disconnect=lambda scope, conn: notify_left(scope),
    )
```

For each `ChangeEvent` on the scope, the stream:

::::{steps}
:::{step} Skips self-caused events
If `origin` is set and matches the event's `origin`, the event is skipped.
:::{/step}
:::{step} Applies audience filtering
When the event has an `audience`, only connections whose `user_id` is in it receive it.
:::{/step}
:::{step} Looks up affected blocks
`DependencyIndex.affected_blocks(changed_paths)` expands derived/prefix paths and returns the blocks to re-render.
:::{/step}
:::{step} Builds fresh context
Calls `context_builder(changed_paths)` when the builder takes one argument, or `context_builder()` for the zero-argument form.
:::{/step}
:::{step} Yields a fragment per block
Each affected block streams as a `Fragment` targeting its DOM id.
:::{/step}
::::{/steps}

**Selective context.** The one-argument `context_builder` receives the exact `frozenset[str]` of changed paths (after index expansion), so an expensive page can load only what changed:

```python
def build_doc_context(changed_paths: frozenset[str]) -> dict:
    if "doc.comments" in changed_paths:
        return {"comments": store.load_comments()}
    return {"doc": store.load_doc()}
```

**Error boundary.** If `context_builder()` raises, that one event is skipped and the stream stays alive; the next change retries with fresh data.

:::{changed} 0.8
`context_builder` may now accept one argument — the `frozenset[str]` of changed paths — for selective context assembly. The zero-argument form still works.
:::

### Audience-filtered notifications

Set `audience` when a change matters to only some viewers:

```python
bus.emit_sync(ChangeEvent(
    scope="doc-42",
    changed_paths=frozenset({"notifications"}),
    audience=frozenset({"alice", "bob"}),
))
```

Subscribers without a `ConnectionInfo`, or with a `user_id` outside the audience, do not receive it. Broadcast events keep `audience=None`.

## Gotchas

:::{warning}
**Events drop silently under back-pressure.** Each subscriber has a bounded queue (`maxsize`, default 256). When a subscriber's queue is full, the bus drops that event for that subscriber rather than blocking the emitter. Drops are logged at `WARNING` (throttled per scope) and counted in `bus.dropped_count` — watch that counter if a slow client might fall behind. A dropped event is not retried.
:::

Calling `bus.close("doc-42")` signals every subscriber on that scope to stop; `bus.close()` with no argument closes all scopes.

## Advanced

:::{dropdown} Building and inspecting the dependency index by hand
Most apps get the index from `register_template()` at startup. The lower-level surface below is for the rare case where you register, query, or debug the mapping directly.

**Register only the blocks behind `sse-swap` elements.** Scans the raw template source and registers just those blocks, with their DOM ids — handy when most of a page is static:

```python
source = env.loader.get_source(env, "page.html")[0]
index.register_from_sse_swaps(env, "page.html", source,
    exclude_blocks={"editor_content"},  # client-managed, don't re-render
)
```

**Query the mapping:**

```python
blocks = index.affected_blocks(frozenset({"doc.content"}))
# -> [BlockRef(template_name="page.html", block_name="content"), ...]

paths = index.block_dependencies("page.html", "content")
# -> the context paths that can cause that block to re-render
```

**Trace an expansion** with `explain_affected()` — it shows the derived-path chain and the blocks each change resolves to:

```python
index.explain_affected(frozenset({"doc.content"}))
# {
#   "original_paths": {"doc.content"},
#   "expanded_paths": {"doc.content", "doc.word_count", "doc.summary"},
#   "derived_paths": {"doc.word_count", "doc.summary"},
#   "affected_blocks": [{"template": "page.html", "block": "content", "target": "doc-body"}, ...]
# }
```
:::{/dropdown}

:::{dropdown} Tuning queue depth and watching throughput
The bus exposes per-subscriber back-pressure tuning and three observability counters:

```python
bus = ReactiveBus(maxsize=64)   # per-subscriber queue depth; default 256

bus.emitted_count      # total events emitted (including dropped)
bus.dropped_count      # events lost to full subscriber queues
bus.subscriber_count   # active subscribers across all scopes
```

Pass `on_drop=callback` to `ReactiveBus(...)` for a custom hook on each drop (`(scope, event) -> None`). Keep it fast — it runs on the emit path.
:::{/dropdown}

::::{dropdown} Validating the index with app.check()
`app.check()` (and the `chirp check` CLI) validates the reactive system at startup. The checks run only when you register the index as contract data:

```python
app.set_contract_check_data("reactive_index", index)
app.set_contract_check_data("reactive_emitted_paths", {"tasks", "presence"})
app.set_contract_check_data("reactive_connection_scopes", {"board"})

# Add only when you emit ChangeEvent(..., audience=...).
app.set_contract_check_data("reactive_audience_scopes", {"board"})
```

Four categories fire:

:::{list-table}
:header-rows: 1

* - Category
  - Severity
  - Catches
* - `reactive_block`
  - ERROR
  - A `BlockRef` points at a template block that does not exist (typo or renamed block).
* - `reactive_cycle`
  - WARNING
  - The derivation graph contains a cycle.
* - `reactive_paths`
  - WARNING
  - A declared emitted path is not registered in the index.
* - `reactive_audience`
  - WARNING
  - An audience-filtered scope has no connection-aware stream to match against.
:::

Keep `reactive_emitted_paths` in sync with the `changed_paths` your code emits. See [[docs/quality/contracts-debugging/categories|contract categories]] for every category and how severities behave per environment.
::::{/dropdown}

`ReactiveBus` is fully thread-safe and `DependencyIndex` is read-only after construction, so you build the index once at startup and share both across every handler. See [[docs/about/thread-safety|Thread Safety]] for the guarantees behind that.

## Related

:::{related}
:::
