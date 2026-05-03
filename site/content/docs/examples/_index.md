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

Run examples from the repository root with `PYTHONPATH=src` so they use the
checkout you are reading. Each example has a focused job: learn return types,
practice htmx fragments, validate Suspense, exercise SSE, or see the app-shell
lane.

:::{cards}
:columns: 2
:gap: medium

:::{card} RAG Demo
:icon: ai-chatgpt
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
