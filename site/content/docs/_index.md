---
title: Documentation
description: Documentation for building HTMX-driven, server-rendered web apps with Chirp
draft: false
weight: 10
lang: en
type: doc
keywords: [chirp, python web framework, htmx, server-rendered, html fragments, streaming]
category: overview

cascade:
  type: doc
---

## Get Oriented

Chirp is a Python framework for hypermedia-native apps: you return HTML — pages,
fragments, streams, and Server-Sent Events — and
[[docs/about/core-concepts/return-values|the return type expresses the intent]].

New here? Start with **Get Started** ([[docs/get-started/learning-path|learning path]]).
Sizing it up? Read **About**. Already building? Jump to **Build Apps** or the
**Reference**.

## How this site is organized

| Lane | Use when |
|------|----------|
| [Get Started](/chirp/docs/get-started/) | First hour — install, quickstart, [learning path](/chirp/docs/get-started/learning-path/) |
| [About](/chirp/docs/about/) | Why Chirp, mental model, comparison, non-goals |
| [Build Apps](/chirp/docs/build-apps/) | Implementing a feature (routing, forms, SSE, …) |
| [Tutorials](/chirp/docs/tutorials/) | Guided multi-step builds (Flask migration, auth, patterns) |
| [Examples](/chirp/docs/examples/) | Copy runnable code — tier 1 → 2 → 3 |
| [Quality & Operations](/chirp/docs/quality/) | `chirp check`, tests, deployment |
| [Reference](/chirp/docs/reference/) | Symbol lookup, [glossary](/chirp/docs/reference/glossary/), CLI |

Machine-readable doc index: [`/chirp/llms.txt`](/chirp/llms.txt) (generated on site build).

:::{cards}
:columns: 2
:gap: medium

:::{card} Get Started
:icon: rocket
:link: /chirp/docs/get-started/
Install Chirp, follow the learning path, and build your first fragment app.
:::{/card}

:::{card} About
:icon: info
:link: /chirp/docs/about/
What Chirp is, why it is different, and how the return-type model works.
:::{/card}

:::{card} Build Apps
:icon: layers
:link: /chirp/docs/build-apps/
Pages, fragments, forms, streaming, UI extensions, and request pipelines.
:::{/card}

:::{card} Quality and Operations
:icon: check-circle
:link: /chirp/docs/quality/
Contracts, debugging, tests, deployment, and production operations.
:::{/card}

:::{/cards}

---

## Reference and Examples

:::{cards}
:columns: 2
:gap: medium

:::{card} Reference
:icon: file-text
:link: /chirp/docs/reference/
API reference, glossary, errors, and CLI.
:::{/card}

:::{card} Examples
:icon: cube
:link: /chirp/docs/examples/
Runnable apps by tier — contacts, shell, Lucky Cat capstone.
:::{/card}

:::{card} Applied Tutorials
:icon: graduation-cap
:link: /chirp/docs/tutorials/
Step-by-step walkthroughs for migrations, htmx patterns, and UI interactions.
:::{/card}

:::{/cards}
