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

New to Chirp? [[docs/get-started/learning-path|Follow the learning path]], then work the
**tiers below in order**.

## Learning path

| Tier | Example | Teaches |
|------|---------|---------|
| **1 — Basics** | [[docs/examples/contacts|Contacts]] (standalone) | Routes, forms, `Page` / `Fragment`, OOB |
| **2 — App shell** | [[docs/examples/contacts-shell|Contacts shell]] | ChirpUI shell, `_actions.py`, boosted nav |
| **3 — Capstone** | [[docs/examples/lucky-cat|Lucky Cat]] | Signals, Suspense, SSE, OOB, secure stack |

**Tier 3 live demo:** [luckycat-production.up.railway.app](https://luckycat-production.up.railway.app)

:::{cards}
:columns: 2
:gap: medium

:::{card} Contacts
:icon: users
:link: /chirp/docs/examples/contacts/
:description: Tier 1 — plain htmx CRUD with validation and OOB swaps
The baseline app for forms, inline edit, search, and fragment updates.
:::{/card}

:::{card} Returns Gallery
:icon: layers
:link: /chirp/docs/examples/returns-gallery/
:description: Tier 1 — every Chirp response type on one page
Learn when to use `Template`, `Page`, `Fragment`, `OOB`, `Suspense`, `Stream`, and `EventStream`.
:::{/card}

:::{card} SSE
:icon: network
:link: /chirp/docs/examples/sse/
:description: Tier 1 — minimal Server-Sent Events
The smallest post-load update channel example.
:::{/card}

:::{card} Suspense Dashboard
:icon: zap
:link: /chirp/docs/examples/suspense-dashboard/
:description: Tier 1 — shell-first initial render with deferred blocks
Skeleton placeholders resolve into OOB swaps as async data finishes.
:::{/card}

:::{card} Contacts Shell
:icon: users
:link: /chirp/docs/examples/contacts-shell/
:description: Tier 2 — CRUD with chirp-ui app shell and boosted nav
Full CRUD app with app shell, boosted navigation, and fragment swaps.
:::{/card}

:::{card} Kanban Shell
:icon: sidebar
:link: /chirp/docs/examples/kanban-shell/
:description: Tier 2 — drag-and-drop board with OOB and SSE
Real-time board with multi-fragment updates and SSE live sync.
:::{/card}

:::{card} Lucky Cat
:icon: rocket
:link: /chirp/docs/examples/lucky-cat/
:description: Tier 3 capstone — simulated trading floor · live demo
Signals, Suspense, SSE, OOB, and auth on one app shell. Complete tiers 1–2 first.
:::{/card}

:::{card} RAG Demo
:icon: sparkle
:link: /chirp/docs/examples/rag-demo/
:description: Tier 3 — streaming AI Q&A with cited sources
Fragments, SSE, and free-threading — after you know the return-type model.
:::{/card}

:::{/cards}

:::{tip} Running an example
Run examples from the repository root with `PYTHONPATH=src` so they use the
checkout you are reading — for example `PYTHONPATH=src python examples/chirpui/pages_shell/app.py`.
:::
