---
title: SSE Patterns
description: Four update patterns for real-time applications
draft: false
weight: 25
lang: en
type: doc
tags: [sse, real-time, patterns, htmx]
keywords: [sse, patterns, contenteditable, streaming, reactive, htmx]
category: guide
---

## Overview

Real-time applications mix different update strategies on the same page. A collaborative editor, for example, has a status badge (server-rendered), an editing surface (client-managed), an AI chat (streaming tokens), and CRUD actions (one-shot). Each requires a different approach.

This guide covers the four patterns and when to use each.

## Pattern 1: Display-Only Reactive

**Use for**: status badges, counters, presence lists, dashboards -- any element where the server is the sole rendering authority and the client is a passive display.

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
  <span id="status" sse-swap="status">
    {% block status_block %}v{{ stats.version }}{% endblock %}
  </span>
</div>
```

Key rules:

- `Fragment.target` becomes the SSE event name.
- `sse-swap` must be on a **child** of `sse-connect`, never the same element.
- Add `hx-disinherit="hx-target hx-swap"` on the `sse-connect` element to prevent layout-level `hx-target` from bleeding into SSE swaps.

`chirp check` validates all three rules at compile time.

## Pattern 2: Client-Managed Surfaces

**Use for**: `contenteditable` editors, canvas drawing, drag-and-drop, code editors -- any element where the browser owns the DOM tree.

The browser maintains internal state (cursor position, undo history, selection, paragraph elements) that cannot survive innerHTML replacement. **Do not register these blocks in the reactive dependency index.**

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

```python
# Dependency index: editor block is NOT registered
index.register_from_sse_swaps(env, "page.html", source,
                              exclude_blocks={"editor_content"})

# Derived paths: version always changes when content changes,
# so version-dependent blocks update automatically even if the
# store only emits {"doc.content"}.
index.derive("doc.version", from_paths={"doc.content"})
```

> **Derived paths** let you declare computed relationships between context paths. When a source path changes, all derived paths are automatically included in the affected set. Stores emit what actually mutated, and display blocks that depend on computed values update without extra wiring. See `DependencyIndex.derive()`.

For multi-user collaboration, send OT/CRDT operations over SSE as JSON (via `SSEEvent`) and apply them client-side. Do not re-render HTML.

## Pattern 3: Streaming Append

**Use for**: AI chat tokens, live logs, activity feeds -- content that arrives incrementally and appends to a container.

This pattern has two phases: a POST that returns scaffolding, and an SSE stream that fills it in.

Phase 1 -- POST returns the scaffolding:

```python
async def post(doc_id: str, request: Request) -> Fragment:
    form = await request.form()
    message = form["message"]
    return Fragment("_chat.html", "chat_start",
                    doc_id=doc_id, user_content=message)
```

```html
{# Phase 1: POST response -- user bubble + AI bubble with SSE #}
{% block chat_start %}
<div class="msg msg-user">{{ user_content }}</div>
<div class="msg msg-ai"
     hx-ext="sse"
     sse-connect="/doc/{{ doc_id }}/chat/stream"
     sse-close="done">
  <span class="tokens" sse-swap="fragment" hx-swap="beforeend"></span>
  <span class="typing-cursor"></span>
</div>
{% endblock %}
```

Phase 2 -- SSE streams tokens:

```python
def get(doc_id: str) -> EventStream:
    async def generate():
        async for token in ai_session.stream_reply():
            yield Fragment("_chat.html", "chat_token", token=token)
        yield SSEEvent(event="done", data="complete")
    return EventStream(generate())
```

```html
{# Phase 2: each token #}
{%- block chat_token -%}
{%- if token is defined %}{{ token }}{% end -%}
{%- end -%}
```

Key rules:

- `sse-swap` is on the inner `<span>`, not the `sse-connect` div.
- `hx-swap="beforeend"` appends tokens instead of replacing.
- `sse-close="done"` closes the connection when streaming finishes.
- The `Fragment.target` defaults to `"fragment"` when not set.

## Pattern 4: One-Shot Mutations

**Use for**: form submissions, delete buttons, rename actions -- requests that produce a single response and are done.

```python
async def post(doc_id: str, request: Request) -> Action:
    store.rename(doc_id, title=(await request.form())["title"])
    return Action(trigger="renamed")
```

Chirp provides several return types for this pattern:

| Return Type | Behavior |
|---|---|
| `Action()` | 204 No Content -- side effect only, no swap |
| `Action(trigger="event")` | 204 + `HX-Trigger` header |
| `Fragment(...)` | Render a block, swap into the target |
| `OOB(main, *oob)` | Primary swap + out-of-band fragment swaps |
| `ValidationError(...)` | 422 + re-rendered form with errors |

## Mixing Patterns on One Page

Most pages combine multiple patterns. The key principle: **establish scope boundaries** so patterns don't interfere with each other.

```html
<body hx-boost="true" hx-target="#app-content">
  <nav>...</nav>
  <main id="app-content">
    <!-- SSE scope boundary: hx-disinherit prevents
         layout-level hx-target from reaching SSE swaps -->
    <div hx-ext="sse"
         sse-connect="/doc/{{ doc.id }}/stream"
         hx-disinherit="hx-target hx-swap">

      <!-- Pattern 1: display-only reactive -->
      <span id="status" sse-swap="status">v{{ doc.version }}</span>
      <span id="title" sse-swap="title">{{ doc.title }}</span>

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

Rules for mixing:

1. **SSE containers get `hx-disinherit`** -- isolate SSE swaps from layout targets.
2. **Navigation links restore `hx-target`** -- add `hx-target="#app-content"` on toolbar/nav containers inside the SSE scope.
3. **Client-managed elements have no `sse-swap`** -- they are invisible to the reactive system.
4. **Nested SSE connections** (like chat) put `sse-swap` on a child, never on the `sse-connect` element.

## Compile-Time Validation

`chirp check` catches common SSE mistakes:

| Check | Severity | What it catches |
|---|---|---|
| `sse_self_swap` | ERROR | `sse-swap` on the same element as `sse-connect` |
| `sse_scope` | WARNING | `sse-connect` inside broad `hx-target` without `hx-disinherit` |
| `swap_safety` | WARNING | `sse-swap` element inheriting a broad `hx-target` |

Run `chirp check` during development to catch these before they become runtime mysteries.
