---
title: About
description: Architecture, philosophy, framework comparisons, and thread-safety guidance for Chirp
draft: false
weight: 100
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
This section explains the framework's structure and where it fits.

:::{card} Architecture
:icon: box
:link: ./architecture
:description: Three-layer design
Surface, core, and engine layers.
:::{/card}

:::{card} Philosophy
:icon: compass
:link: ./philosophy
:description: Design principles
The instincts that shape every decision.
:::{/card}

:::{card} Comparison
:icon: bar-chart
:link: ./comparison
:description: Chirp vs Flask vs FastAPI vs Django
When to use what, and why Chirp exists as a framework for HTML over the wire.
:::{/card}

:::{card} Thread Safety
:icon: shield
:link: ./thread-safety
:description: Free-threading patterns
How Chirp makes data races structurally impossible.
:::{/card}

:::{card} Ecosystem
:icon: layers
:link: ./ecosystem
:description: The Bengal stack
All seven projects in the reactive Python stack.
:::{/card}

:::{/cards}
