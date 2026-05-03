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

Chirp's docs are organized around the work you are trying to do: start an app,
build pages, render fragments, handle mutations, stream updates, validate
contracts, and ship safely. Start with **Get Started** if you are new; otherwise
jump to the cluster that matches the surface you are changing.

:::{cards}
:columns: 2
:gap: medium

:::{card} Get Started
:icon: rocket
:link: /chirp/docs/get-started/
Install Chirp, scaffold an app, and build the first fragment-backed page.
:::{/card}

:::{card} Build Pages and Navigation
:icon: git-branch
:link: /chirp/docs/routing/
Routes, filesystem pages, app lifecycle, shells, and boosted navigation.
:::{/card}

:::{card} Render HTML Fragments
:icon: layers
:link: /chirp/docs/templates/
Templates, `Page`, `Fragment`, OOB swaps, block targets, and render plans.
:::{/card}

:::{card} Handle Forms and Mutations
:icon: check-square
:link: /chirp/docs/data/forms-validation/
Form parsing, validation, CSRF-aware mutations, redirects, and inline edits.
:::{/card}

:::{/cards}

---

## Build Dynamic Surfaces

:::{cards}
:columns: 2
:gap: medium

:::{card} Stream and Push Updates
:icon: zap
:link: /chirp/docs/streaming/
`Stream`, `Suspense`, `EventStream`, SSE patterns, and reactive updates.
:::{/card}

:::{card} Validate Contracts and Debug UI
:icon: shield
:link: /chirp/docs/reference/route-contract/
`app.check`, `chirp check`, DevTools, debug headers, and swap failure modes.
:::{/card}

:::{card} Ship and Operate Apps
:icon: server
:link: /chirp/docs/deployment/
Configuration, middleware, sessions, security headers, static files, and deploys.
:::{/card}

:::{card} Use Data Safely
:icon: database
:link: /chirp/docs/data/
Database helpers, query builder, migrations, pagination, and optional extras.
:::{/card}

:::{card} Extend Chirp
:icon: wrench
:link: /chirp/docs/guides/tools/
Middleware, template filters, MCP tools, plugins, and extension boundaries.
:::{/card}

:::{/cards}

---

## Reference and Examples

:::{cards}
:columns: 2
:gap: medium

:::{card} Core Concepts
:icon: book-open
:link: /chirp/docs/core-concepts/
Return values, app lifecycle, configuration, and the type-driven model.
:::{/card}

:::{card} Guides
:icon: book
:link: /chirp/docs/guides/
Focused how-to material for shells, accessibility, Alpine, islands, and tools.
:::{/card}

:::{card} Examples
:icon: cube
:link: /chirp/docs/examples/
Full-featured apps: contacts, dashboards, RAG, streaming, fragments, and SSE.
:::{/card}

:::{card} Reference
:icon: file-text
:link: /chirp/docs/reference/
Complete API reference, error codes, and configuration.
:::{/card}

:::{card} Testing
:icon: check-circle
:link: /chirp/docs/testing/
`TestClient`, fragment assertions, SSE testing, and executable contracts.
:::{/card}

:::{card} About
:icon: info
:link: /chirp/docs/about/
Architecture, philosophy, framework comparisons, and thread safety.
:::{/card}

:::{/cards}
