---
title: About
description: Architecture, philosophy, comparisons, and thread safety
draft: false
weight: 100
lang: en
type: doc
tags: [about, architecture, philosophy]
keywords: [architecture, philosophy, comparison, thread-safety, design]
category: explanation
icon: info

cascade:
  type: doc
---

:::{cards}
:columns: 2
:gap: medium

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
When to use what, and why Chirp exists.
:::{/card}

:::{card} Thread Safety
:icon: shield
:link: ./thread-safety
:description: Free-threading patterns
How Chirp makes data races structurally impossible.
:::{/card}

:::{/cards}
