---
title: Documentation
description: Documentation for building HTMX-driven, server-rendered web apps with the Chirp Python web framework
draft: false
weight: 10
lang: en
type: doc
keywords: [chirp, python web framework, htmx, server-rendered, html fragments, streaming]
category: overview

cascade:
  type: doc
---

## Learn Chirp

Chirp is a Python web framework for HTMX, server-rendered UI, HTML fragments,
streaming HTML, and Server-Sent Events. Start with quickstart and core concepts, then
move into templates, routing, streaming, and production deployment.

:::{cards}
:columns: 2
:gap: medium

:::{card} Get Started
:icon: rocket
:link: ./get-started/
Install Chirp and build your first app in minutes.
:::{/card}

:::{card} Core Concepts
:icon: book-open
:link: ./core-concepts/
App lifecycle, return values, and configuration.
:::{/card}

:::{card} Templates
:icon: layers
:link: ./templates/
Rendering, fragments, Page, OOB swaps, and filters.
:::{/card}

:::{card} Routing
:icon: git-branch
:link: ./routing/
Routes, path parameters, request, and response.
:::{/card}

:::{/cards}

---

## Go Deeper

:::{cards}
:columns: 2
:gap: medium

:::{card} Middleware
:icon: sliders
:link: ./middleware/
Protocol definition, built-in middleware, custom middleware.
:::{/card}

:::{card} Streaming
:icon: zap
:link: ./streaming/
Streaming HTML, Server-Sent Events, real-time patterns.
:::{/card}

:::{card} Data
:icon: database
:link: ./data/
Database access, form parsing, and validation.
:::{/card}

:::{card} Testing
:icon: check-circle
:link: ./testing/
TestClient, fragment assertions, SSE testing.
:::{/card}

:::{card} Deployment
:icon: server
:link: ./deployment/
Production deployment with `chirp run myapp:app --production` and Pounce.
:::{/card}

::::{card} htmx Patterns
:icon: repeat
:link: ./tutorials/htmx-patterns
Search, inline edit, infinite scroll, and fragment-based interaction patterns.
::::{/card}

:::{/cards}

---

## Reference & More

:::{cards}
:columns: 2
:gap: medium

:::{card} About
:icon: info
:link: ./about/
Architecture, philosophy, framework comparisons, and thread safety.
:::{/card}

:::{card} Tutorials
:icon: graduation-cap
:link: ./tutorials/
Step-by-step guides for common patterns and migrations.
:::{/card}

:::{card} Guides
:icon: book
:link: ./guides/
Accessibility, best practices, and patterns.
:::{/card}

:::{card} Examples
:icon: box
:link: ./examples/
Full-featured apps: RAG demo with streaming AI, fragments, and SSE.
:::{/card}

:::{card} Reference
:icon: file-text
:link: ./reference/
Complete API reference, error codes, and configuration.
:::{/card}

:::{card} Troubleshooting
:icon: help-circle
Having issues? Check the tutorials or open an issue on GitHub.
:::{/card}

:::{/cards}
