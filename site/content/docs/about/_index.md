---
title: About
description: Architecture, philosophy, framework comparisons, and thread-safety guidance for Chirp
draft: false
weight: 1
lang: en
type: doc
tags: [about, architecture, philosophy]
keywords: [python web framework, architecture, comparison, thread-safety, htmx]
category: explanation
icon: info

cascade:
  type: doc
---

:::{cards}
:columns: 2
:gap: medium

Chirp focuses on server-rendered UI, HTML fragments, and browser-native interaction.
This section explains the framework's structure, fit, and core model.

:::{card} Philosophy
:icon: compass
:link: /chirp/docs/about/philosophy/
:description: Design principles
The instincts that shape every decision.
:::{/card}

:::{card} Non-Goals
:icon: ban
:link: /chirp/docs/about/non-goals/
:description: The bright lines
What the core won't do — and the honest alternative for each.
:::{/card}

:::{card} Architecture
:icon: cube
:link: /chirp/docs/about/architecture/
:description: Three-layer design
Surface, core, and engine layers.
:::{/card}

:::{card} When to Use Chirp
:icon: workflow
:link: /chirp/docs/about/comparison/
:description: Chirp vs Flask vs FastAPI vs Django
When to use what, and why Chirp exists as a framework for HTML over the wire.
:::{/card}

:::{card} Thread Safety
:icon: shield
:link: /chirp/docs/about/thread-safety/
:description: Free-threading patterns
How Chirp makes data races structurally impossible.
:::{/card}

:::{card} Bengal Ecosystem
:icon: layers
:link: /chirp/docs/about/ecosystem/
:description: The Bengal stack
All seven projects in the reactive Python stack.
:::{/card}

:::{card} Core Concepts
:icon: book-open
:link: /chirp/docs/about/core-concepts/
:description: The framework mental model
How return values, freezing, configuration, and contracts fit together.
:::{/card}

:::{/cards}
