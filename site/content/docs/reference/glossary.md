---
title: Glossary
description: Chirp and hypermedia terminology used across the docs
draft: false
weight: 10
lang: en
type: doc
tags: [reference, glossary, terminology]
keywords: [glossary, fragment, page, oob, suspense, eventstream, signal, shape, contract]
category: reference
---

Short definitions for terms used throughout the documentation. For return-type
behavior, see [[docs/about/core-concepts/return-values|Return values]].

## Return types and rendering

| Term | Meaning |
|------|---------|
| **Template** | Render a full page through layouts. |
| **Fragment** | Render one named block from a template — the usual htmx partial. |
| **Page** | Auto-negotiate: full page for browser navigation, named block for htmx. |
| **OOB** (out-of-band) | One response updates multiple DOM targets; includes main content plus extra swap regions. |
| **Stream** | Progressive HTML over one chunked HTTP response; blocks flush as they complete (no shell-first guarantee). |
| **Suspense** | Shell renders first; deferred template blocks stream in as OOB swaps when data resolves. |
| **EventStream** | Long-lived SSE (`text/event-stream`) channel for post-load updates. |
| **FormAction** | Mutation result for forms: fragments for htmx, redirect for full-page posts. |
| **ValidationError** | 422 with re-rendered form fragment (and full page for non-htmx). |
| **SignalEmit** | Emit a server-owned reactive value consumed over the live SSE merge stream. |

## Hypermedia and htmx

| Term | Meaning |
|------|---------|
| **Hypermedia-native** | The app speaks HTML at every layer — not JSON translated into UI on the client. |
| **Content negotiation** | Chirp picks full page vs fragment vs stream from return type and request headers. |
| **Boosted navigation** | htmx-enhanced links that swap `#main` without a full reload (common in app shells). |
| **Swap target** | DOM node (`hx-target`, `id`) that receives swapped HTML. |
| **Contract** | Static rule checked by `chirp check` (routes, blocks, SSE wiring, a11y, …). |

## App structure

| Term | Meaning |
|------|---------|
| **Filesystem routing** | Routes discovered from a `pages/` tree with layouts and reserved files. |
| **`_meta.py`** | Route metadata (title, auth) in filesystem routing. |
| **`_context.py`** | Shared template context for a route subtree. |
| **`_actions.py`** | Shell action definitions for filesystem routes. |
| **App shell** | Persistent chrome (topbar, sidebar) with a main content outlet — often via chirp-ui. |
| **Shape** | `@shape` dataclass: SQL in, frozen row model out; verified by `shapecheck` contracts. |
| **Freeze** | App transitions from mutable setup (routes, middleware) to immutable runtime. |

## Realtime

| Term | Meaning |
|------|---------|
| **Signal** | Server-owned reactive value; templates bind with `signal()` / `signal_block()`; updates via `/_chirp/live` SSE. |
| **`/_chirp/live`** | Auto-registered merge stream for cross-page chrome signals. |
| **Deferred block** | Template block resolved asynchronously in Suspense or reactive pages. |

## Tooling

| Term | Meaning |
|------|---------|
| **`chirp check`** | CLI/static validation of hypermedia surface (routes, hx attrs, blocks, SSE). |
| **Swap Doctor** | Chirp DevTools panel diagnosing htmx swap and inheritance issues. |
| **Category** | Stable contract error handle (e.g. `fragment_target`) for CI policy. |
| **Pounce** | ASGI server used for production Chirp deployments. |
| **Kida** | Template engine; named blocks power fragments and layouts. |

## Examples tier labels

| Term | Meaning |
|------|---------|
| **Tier 1** | Standalone basics — contacts, returns gallery, SSE. |
| **Tier 2** | ChirpUI app shell — contacts_shell, kanban_shell. |
| **Tier 3 capstone** | Composed product demo — Lucky Cat, RAG demo. |

**See also:** [[docs/about/core-concepts/return-values|Return values]] ·
[[docs/build-apps/streaming-updates/realtime-decision-tree|Realtime decision tree]] ·
[[docs/quality/contracts-debugging/categories|Contract categories]]
