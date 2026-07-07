---
title: SSE Patterns
description: Four real-time update patterns, each mapped to the Chirp return type that drives it
draft: false
weight: 25
lang: en
type: doc
tags: [sse, real-time, patterns, htmx]
keywords: [sse, patterns, contenteditable, streaming, reactive, htmx]
category: guide
---

## Overview

Real-time pages rarely use a single update strategy. A collaborative editor has a
status badge the *server* owns, an editing surface the *browser* owns, an AI reply
that streams token by token, and save/delete actions that fire once and finish.
Each of those is a different pattern with a different [[docs/about/core-concepts/return-values|return type]].

This guide names the four patterns, gives the smallest working version of each, and
tells you which return type to reach for. Start with the decision table, then jump to
the pattern you need.

If you are new to the SSE wire format (`sse-connect`, `sse-swap`, event names), read
[[docs/build-apps/streaming-updates/server-sent-events|SSE basics and the wire format]]
first — this page assumes it. For a single value bound in many places, see
[[docs/build-apps/streaming-updates/signals|signals]].

:::{note} Client dialects
The legacy markup examples below describe the htmx 2 rollback tier. The exact
htmx 4 preview uses `hx-sse:connect`, unnamed rendered messages, and
`<hx-partial>` targets. `sse_scope()` selects the right connection shape; do
not mix both dialects on one source element.
:::

## Which pattern?

::::{list-table}
:header-rows: 1

* - Pattern
  - Use for
  - Server owns rendering?
  - Return type
* - **1 — Display-only reactive**
  - Status badges, counters, presence lists, dashboards
  - Yes — client is a passive display
  - `Fragment` (over SSE)
* - **2 — Client-managed surface**
  - `contenteditable`, canvas, drag-and-drop, code editors
  - No — the browser owns the DOM
  - `dict` (JSON)
* - **3 — Streaming append**
  - AI chat tokens, live logs, activity feeds
  - Yes — incremental fragments append
  - `EventStream` + `Fragment`
* - **4 — One-shot mutation**
  - Form submit, delete, rename
  - One response, then done
  - `Action` / `Fragment` / `OOB`
::::

## Pattern 1: Display-only reactive

Use for status badges, counters, presence lists, dashboards — any element where the
server is the sole rendering authority and the client is a passive display.

:::{tip} Reach for
A `Fragment` yielded over SSE. On htmx 2 its `target` becomes the named event;
on htmx 4 it becomes the validated DOM id in an unnamed partial envelope.
:::

```python
# Server: yield Fragment with target matching the sse-swap attribute
async def stream():
    async for change in bus.subscribe(scope):
        yield Fragment("page.html", "status_block",
                       target="status", stats=get_stats())
```

```html
<!-- Client: sse-swap on a CHILD of sse-connect -->
<div hx-ext="sse"
     sse-connect="/stream"
     hx-disinherit="hx-target hx-swap">
  <span id="status" sse-swap="status" hx-target="this">
    {% block status_block %}v{{ stats.version }}{% endblock %}
  </span>
</div>
```

The rules that make this work:

- On htmx 2, `Fragment.target` becomes the SSE event name; a target-less `Fragment` emits an
  unnamed frame that the default `sse-swap="message"` listener receives.
- `sse-swap` must be on a **child** of `sse-connect`, never the same element.
- `hx-disinherit="hx-target hx-swap"` on the `sse-connect` element stops a
  layout-level `hx-target` from bleeding into SSE swaps.
- `hx-target="this"` on each `sse-swap` element targets the swap correctly once
  inheritance is broken.

The same server generator under the htmx 4 preview pairs with native markup:

```html
<div hx-sse:connect="/stream" hx-target="#status">
  <span id="status">{% block status_block %}v{{ stats.version }}{% endblock %}</span>
</div>
```

Chirp sends the targeted `Fragment` as unnamed
`<hx-partial hx-target="#status">…</hx-partial>` data. A named `SSEEvent` is
instead a DOM event and never a rendered swap.

`chirp check myapp:app` validates all four rules at startup. See
[Compile-time validation](#compile-time-validation) below.

## Pattern 2: Client-managed surfaces

Use for `contenteditable` editors, canvas drawing, drag-and-drop, code editors —
any element where the browser owns the DOM tree.

The browser maintains internal state (cursor position, undo history, selection,
paragraph elements) that cannot survive an `innerHTML` replacement. So the server
returns JSON, not rendered HTML, and the block is **not** registered in the reactive
dependency index.

:::{tip} Reach for
A plain `dict` return. Chirp serializes it to JSON; the client applies it.
:::

```python
# Server: return JSON, not rendered HTML
async def post(doc_id: str, request: Request) -> dict:
    edit = parse_edit(await request.json())
    updated = store.apply_edit(edit)
    return {"ok": True, "version": updated.version}
```

```html
<!-- Client: no sse-swap, no reactive rendering -->
<div class="editor"
     id="editor"
     contenteditable="true"
     data-doc-id="{{ doc.id }}"
     data-version="{{ doc.version }}"
>{{ doc.content }}</div>
```

For complex widgets that need framework adapters (React, Svelte, Vue) or custom
logic, use [[docs/build-apps/ui-extensions/islands|Chirp islands]]. Islands provide
a `data-island` mount contract with lifecycle events and optional dynamic adapter
loading. Islands are client-owned surfaces; the server does not swap HTML inside them.

For multi-user collaboration, send OT/CRDT operations over SSE as JSON (via
`SSEEvent`) and apply them client-side. Do not re-render HTML.

:::{dropdown} Advanced: excluding the block and declaring derived paths
This wiring lives on the [[docs/build-apps/streaming-updates/reactive-system|reactive bus]]
index. Exclude a client-managed block so the reactive system never tries to swap it:

```python
# Dependency index: editor block is NOT registered
index.register_from_sse_swaps(env, "page.html", source,
                              exclude_blocks={"editor_content"})

# Derived paths: version always changes when content changes,
# so version-dependent display blocks update even if the store
# only emits {"doc.content"}.
index.derive("doc.version", from_paths={"doc.content"})
```

`index.derive(path, *, from_paths=...)` declares a computed relationship between
context paths: when a source path changes, the derived path joins the affected set
automatically, so display blocks that depend on computed values update without extra
wiring. Full model: [[docs/build-apps/streaming-updates/reactive-system|Reactive System]].
:::{/dropdown}

## Pattern 3: Streaming append

Use for AI chat tokens, live logs, activity feeds — content that arrives
incrementally and appends to a container.

:::{tip} Reach for
An `EventStream` that yields `Fragment`s. The POST returns scaffolding; the stream
fills it in.
:::

This pattern has two phases: a POST that returns the scaffolding, and an SSE stream
that fills it in.

::::{code-tabs}
:sync: chat-phase

```python title="Phase 1 — POST scaffolding"
async def post(doc_id: str, request: Request) -> Fragment:
    form = await request.form()
    message = form["message"]
    return Fragment("_chat.html", "chat_start",
                    doc_id=doc_id, user_content=message)
```

```python title="Phase 2 — SSE stream"
def get(doc_id: str) -> EventStream:
    async def generate():
        async for token in ai_session.stream_reply():
            yield Fragment("_chat.html", "chat_token", token=token)
        yield SSEEvent(event="done", data="complete")
    return EventStream(generate())
```

::::

The matching templates:

```html
{# Phase 1: POST response — user bubble + AI bubble with SSE #}
{% block chat_start %}
<div class="msg msg-user">{{ user_content }}</div>
<div class="msg msg-ai"
     hx-ext="sse"
     sse-connect="/doc/{{ doc_id }}/chat/stream"
     sse-close="done">
  <span class="tokens" sse-swap="message" hx-swap="beforeend"></span>
  <span class="typing-cursor"></span>
</div>
{% endblock %}
```

```html
{# Phase 2: each token #}
{%- block chat_token -%}
{%- if token is defined %}{{ token }}{% end -%}
{%- end -%}
```

The rules that make this work:

- `sse-swap` is on the inner `<span>`, not the `sse-connect` div.
- `hx-swap="beforeend"` appends tokens instead of replacing them.
- `sse-close="done"` closes the connection when streaming finishes.
- A yielded `Fragment` with no `target` emits an unnamed SSE frame, so the default
  htmx `sse-swap="message"` listener receives it.

## Pattern 4: One-shot mutations

Use for form submissions, delete buttons, rename actions — requests that produce a
single response and are done.

:::{tip} Reach for
An `Action` for side-effect-only responses, or a `Fragment`/`OOB` when you do want
to swap.
:::

```python
async def post(doc_id: str, request: Request) -> Action:
    store.rename(doc_id, title=(await request.form())["title"])
    return Action(trigger="renamed")
```

Pick the return type by what the response should do:

| Return type | Behavior |
|---|---|
| `Action()` | `204 No Content` — side effect only, no swap |
| `Action(trigger="event")` | `204` + `HX-Trigger` header |
| `Fragment(...)` | Render a block, swap into the target |
| `OOB(main, *oob)` | Primary swap + out-of-band fragment swaps |
| `ValidationError(...)` | `422` + re-rendered form with errors |

## Mixing patterns on one page

Most real pages combine patterns. The key principle: **establish scope boundaries**
so patterns don't interfere with each other.

```html
<body hx-boost="true" hx-target="#app-content">
  <nav>...</nav>
  <main id="app-content">
    <!-- SSE scope boundary: hx-disinherit prevents layout-level
         hx-target from reaching SSE swaps -->
    <div hx-ext="sse"
         sse-connect="/doc/{{ doc.id }}/stream"
         hx-disinherit="hx-target hx-swap">

      <!-- Pattern 1: display-only reactive -->
      <span id="status" sse-swap="status" hx-target="this">v{{ doc.version }}</span>
      <span id="title" sse-swap="title" hx-target="this">{{ doc.title }}</span>

      <!-- Pattern 2: client-managed (no sse-swap) -->
      <div id="editor" contenteditable="true">{{ doc.content }}</div>

      <!-- Pattern 4: one-shot mutation (explicit hx-target) -->
      <div class="toolbar" hx-target="#app-content">
        <a href="/documents" hx-push-url="true">Back</a>
      </div>

      <!-- Pattern 3: streaming append (nested SSE) -->
      <div id="chat">
        <form hx-post="/doc/{{ doc.id }}/chat"
              hx-target="#chat-messages"
              hx-swap="beforeend">
          <input name="message">
          <button>Send</button>
        </form>
        <div id="chat-messages"></div>
      </div>
    </div>
  </main>
</body>
```

The rules for mixing:

- **Restore `hx-target` on navigation links.** Add `hx-target="#app-content"` on
  toolbar and nav containers inside the SSE scope. Once inheritance is broken, nav
  links need an explicit target.
- **Client-managed elements get no `sse-swap`.** Elements you update from JavaScript
  (chat input, custom widgets) are invisible to the reactive system; put `sse-swap`
  only on elements that receive server-pushed fragments.
- **Nested SSE puts `sse-swap` on a child.** The connect element establishes the
  connection; the swap element receives the fragments — never the same element.

:::{danger}
Every SSE container needs `hx-disinherit="hx-target hx-swap"`. Without it, fragments
swap into the boost target instead of the `sse-swap` sink — silently wiping the whole
content area. This is the one mistake that loses live DOM content; `chirp check` flags
it as an error.
:::

## Multi-swap (RAG-style)

When one SSE stream updates multiple regions (sources, answer, share link), use
multiple `sse-swap` elements inside a single `sse-connect`:

```html
<article hx-ext="sse"
         sse-connect="{{ stream_url }}"
         sse-close="done"
         hx-disinherit="hx-target hx-swap">
  <div class="question-block">...</div>
  <div class="sources" sse-swap="sources" hx-target="this">...</div>
  <div class="answer-section">
    <span class="answer-label">Answer</span>
    <div class="answer" sse-swap="answer" hx-target="this">...</div>
    <div class="share-link-wrap" sse-swap="share_link" hx-target="this"></div>
  </div>
</article>
```

The same two rules from Pattern 1 apply to each region:
`hx-disinherit="hx-target hx-swap"` on the `sse-connect` element isolates every swap
from layout inheritance, and `hx-target="this"` on each `sse-swap` element targets it
correctly. See [[docs/examples/rag-demo|RAG demo]] for the full implementation.

## Reconnect and replay

SSE gives the browser reconnect mechanics, not durable product semantics. When you
yield `SSEEvent(id=...)`, the browser sends the latest id back as `Last-Event-ID`
after reconnect. Chirp exposes that header on the request and formats the `id:` line,
but the product owns the durable cursor and the missed-event query.

Use domain cursors you can query later: notification ids, post ids, database sequence
numbers, or queue offsets. Avoid process-local counters or random ids for
product-critical streams.

```python
async def stream(request):
    last_id = request.headers.get("last-event-id")

    async def events():
        async for item in missed_items_after(last_id):
            yield SSEEvent(event="item", id=str(item.id), data=item.html)
        async for item in live_items():
            yield SSEEvent(event="item", id=str(item.id), data=item.html)

    return EventStream(events())
```

When replay is impossible, send a refresh event for the affected fragment so
reconnecting clients reload it.

:::{note} See also

[[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]] covers the
wire format, `SSEEvent` fields, and connection lifecycle in full.
:::

## Compile-time validation

`chirp check` catches common SSE mistakes at startup, before they reach the browser:

| Check | Severity | What it catches |
|---|---|---|
| `sse_self_swap` | ERROR | `sse-swap` on the same element as `sse-connect` |
| `sse_scope` | ERROR | `sse-connect` inside broad `hx-target` without mitigation |
| `swap_safety` | WARNING | `sse-swap` element inheriting a broad `hx-target` |
| `swap_safety` | INFO | `sse-swap` without `hx-target="this"` (suggests adding it) |
| `select_inheritance` | WARNING | Mutating element may inherit a broad `hx-select` from a layout ancestor, silently discarding fragment responses (see [[docs/build-apps/html-fragments/layout-patterns|Layout Patterns]]) |

Run `chirp check myapp:app` during development to catch these before runtime.

:::{note} See also

[[docs/quality/contracts-debugging/categories|Contract categories]] documents every
check, its severity, and how to override it.
:::

## Advanced

:::{dropdown} DOM structure & layout overflow
Get the swap-target structure right to avoid redundant wrappers and horizontal
overflow.

**Outer element** (layout container): holds padding, border, and flex/grid layout.
It stays in place and is never swapped.

**Inner element** (swap target): carries the `id` that matches `sse-swap`. The
fragment block renders **only** the inner content, not the outer wrapper.

```html
<!-- Outer: layout container (padding, border) -->
<div class="answer">
  <!-- Inner: swap target — fragment content goes here -->
  <div id="answer-body" class="answer-body" sse-swap="answer_body">
    {% block answer_body %}
    <div class="answer-content prose">{{ content }}</div>
    {% endblock %}
  </div>
</div>
```

Avoid nesting elements with the same class (e.g. `.answer-with-copy` inside
`.answer`) — that doubles the padding and border.

For flex or grid children that hold long content (code blocks, wide tables), add
`min-width: 0` and `overflow-x: auto` so the container does not force horizontal page
overflow:

```css
.answer-body { min-width: 0; overflow: hidden; }
.answer-content pre { overflow-x: auto; }
```
:::{/dropdown}

:::{dropdown} Operating the reactive bus (counters, queue depth)
The `ReactiveBus` exposes observability counters and a tunable per-subscriber queue
depth. These are operator concerns; the bus model lives on the
[[docs/build-apps/streaming-updates/reactive-system|Reactive System]] page.

```python
from chirp.pages.reactive import ReactiveBus

bus = ReactiveBus(maxsize=64)   # default: 256

bus.emitted_count      # total events emitted (including dropped)
bus.dropped_count      # events lost to full subscriber queues
bus.subscriber_count   # active subscribers across all scopes
```

A small `maxsize` gives tight back-pressure (low latency); a large one tolerates
bursts. When a subscriber's queue is full, events are dropped and `dropped_count`
increments — monitor it to detect slow consumers. Full reference:
[[docs/build-apps/streaming-updates/reactive-system|Reactive System]].
:::{/dropdown}

## See also

:::{note} See also

[[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]] for the
wire format · [[docs/build-apps/streaming-updates/reactive-system|Reactive System]]
for automatic SSE updates from data changes ·
[[docs/build-apps/streaming-updates/signals|signals]] for one value bound in many
places · [[docs/examples/rag-demo|RAG demo]] for a worked multi-swap stream.
:::
