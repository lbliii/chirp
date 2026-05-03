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

Chirp's docs are organized around durable jobs: understand the framework,
start an app, build pages, render fragments, handle forms and data, stream
updates, shape UI, test contracts, and ship safely. Start with **About** for
the why and fit, then **Get Started** for the first working app.

:::{cards}
:columns: 2
:gap: medium

:::{card} About
:icon: info
:link: /chirp/docs/about/
Architecture, philosophy, framework comparisons, and thread safety.
:::{/card}

:::{card} Get Started
:icon: rocket
:link: /chirp/docs/get-started/
Install Chirp, scaffold an app, and build the first fragment-backed page.
:::{/card}

:::{card} Understand Chirp
:icon: book-open
:link: /chirp/docs/core-concepts/
Return values, app lifecycle, configuration, and the type-driven model.
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

:::{card} Handle Forms and Data
:icon: check-square
:link: /chirp/docs/data/
Form parsing, validation, query helpers, migrations, and optional data extras.
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
:link: /chirp/docs/contracts/debugging-swaps/
`app.check`, `chirp check`, DevTools, debug headers, and swap failure modes.
:::{/card}

:::{card} Shape UI and Extensions
:icon: wrench
:link: /chirp/docs/guides/
Shells, swap debugging, accessibility, Alpine, ChirpUI, islands, and tools.
:::{/card}

:::{card} Shape Requests
:icon: settings
:link: /chirp/docs/middleware/
Middleware for CORS, static files, sessions, auth, CSRF, and custom pipelines.
:::{/card}

:::{card} Test Apps and Contracts
:icon: check-circle
:link: /chirp/docs/testing/
`TestClient`, fragment assertions, SSE testing, and executable contracts.
:::{/card}

:::{card} Ship and Operate Apps
:icon: server
:link: /chirp/docs/deployment/
Production deployment, Pounce, Docker, Kubernetes, metrics, and runtime config.
:::{/card}

:::{/cards}

---

## Reference and Examples

:::{cards}
:columns: 2
:gap: medium

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

:::{card} Applied Tutorials
:icon: graduation-cap
:link: /chirp/docs/tutorials/
Step-by-step walkthroughs for migrations, htmx patterns, and UI interactions.
:::{/card}

:::{/cards}
