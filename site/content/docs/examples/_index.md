---
title: Examples
description: Runnable Chirp applications organized by the framework surface they teach
draft: false
weight: 100
lang: en
type: doc
tags: [examples, demos, rag, sse, streaming]
keywords: [examples, demos, rag, sse, streaming, fragments]
category: tutorial
icon: cube

cascade:
  type: doc
---

## Canonical Examples

Every example here is a runnable Chirp app you can copy from. Each one isolates
one part of the framework surface — [[docs/about/core-concepts/return-values|return types]],
htmx fragments, Suspense, SSE, or the chirp-ui app shell — so you can see the
idiomatic pattern in working code.

New to Chirp? [[docs/get-started/_index|Start with the basics]], then work the
**learning path** below. Already fluent in hypermedia? Jump to **RAG Demo** or
**Lucky Cat** for the full app-shell and
[[docs/build-apps/streaming-updates/realtime-decision-tree|streaming and realtime patterns]].

## Learning path

| Tier | Example | Teaches |
|------|---------|---------|
| **1 — Basics** | [[docs/examples/contacts|Contacts]] (standalone) | Routes, forms, `Page` / `Fragment`, OOB |
| **2 — App shell** | [[docs/examples/contacts-shell|Contacts shell]] | ChirpUI shell, `_actions.py`, boosted nav |
| **3 — Capstone** | [[docs/examples/lucky-cat|Lucky Cat]] | Signals, Suspense, SSE, OOB, secure stack |

:::{cards}
:columns: 2
:gap: medium

:::{card} Lucky Cat
:icon: rocket
:link: /chirp/docs/examples/lucky-cat/
:description: Maneki-neko $MEOW simulated trading-floor UI — markets, trade flow, Suspense portfolio, and a command palette
The marquee ChirpUI app-shell demo: trade `FormAction`/`ValidationError`, `Suspense`, and chrome bound to server-owned `signal()`s.
:::{/card}

:::{card} RAG Demo
:icon: sparkle
:link: /chirp/docs/examples/rag-demo/
:description: Streaming AI Q&A with cited sources, dual-model comparison, and zero client JS
The flagship Chirp example: fragments, SSE, event delegation, and free-threading.
:::{/card}

:::{card} Returns Gallery
:icon: layers
:link: /chirp/docs/examples/returns-gallery/
:description: Every Chirp response type on one page
Learn when to use `Template`, `Page`, `Fragment`, `OOB`, `Suspense`, `Stream`, and `EventStream`.
:::{/card}

:::{card} Contacts
:icon: users
:link: /chirp/docs/examples/contacts/
:description: Plain htmx CRUD with validation and OOB swaps
The baseline app for forms, inline edit, search, and fragment updates.
:::{/card}

:::{card} Suspense Dashboard
:icon: zap
:link: /chirp/docs/examples/suspense-dashboard/
:description: Shell-first initial render with deferred blocks
Skeleton placeholders resolve into OOB swaps as async data finishes.
:::{/card}

:::{card} SSE
:icon: network
:link: /chirp/docs/examples/sse/
:description: Minimal Server-Sent Events with strings, SSEEvent, and Fragment payloads
The smallest post-load update channel example.
:::{/card}

:::{card} Contacts Shell
:icon: users
:link: /chirp/docs/examples/contacts-shell/
:description: CRUD contacts with chirp-ui app shell, sidebar navigation, and full test coverage
Full CRUD app with app shell, boosted navigation, and fragment swaps.
:::{/card}

:::{card} Kanban Shell
:icon: sidebar
:link: /chirp/docs/examples/kanban-shell/
:description: Drag-and-drop Kanban board with OOB swaps, SSE, and toast notifications
Real-time board with multi-fragment updates and SSE live sync.
:::{/card}

:::{/cards}

:::{tip} Running an example
Run examples from the repository root with `PYTHONPATH=src` so they use the
checkout you are reading — for example `PYTHONPATH=src python examples/chirpui/pages_shell/app.py`.
:::
