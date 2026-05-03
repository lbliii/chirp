---
title: Build Apps
description: Pages, fragments, forms, streaming, UI extensions, and request pipelines in Chirp
draft: false
weight: 10
lang: en
type: doc
tags: [build, pages, fragments, forms, streaming, middleware]
keywords: [chirp, pages, fragments, forms, streaming, htmx, middleware]
category: guide
icon: layers

cascade:
  type: doc
---

Use this section when you are shaping the application surface: URLs, page
directories, named template blocks, form mutations, streaming updates, shell
UI, and middleware around requests.

:::{cards}
:columns: 2
:gap: medium

:::{card} Pages and Navigation
:icon: git-branch
:link: /chirp/docs/build-apps/pages-navigation/
Routes, filesystem pages, route metadata, mounting, and request/response basics.
:::{/card}

:::{card} HTML Fragments
:icon: layers
:link: /chirp/docs/build-apps/html-fragments/
Templates, named blocks, `Page`, `Fragment`, OOB swaps, and Kida integration.
:::{/card}

:::{card} Forms and Data
:icon: check-square
:link: /chirp/docs/build-apps/forms-data/
Form parsing, validation, query helpers, migrations, and optional data extras.
:::{/card}

:::{card} Streaming and Updates
:icon: zap
:link: /chirp/docs/build-apps/streaming-updates/
`Stream`, `Suspense`, `EventStream`, SSE patterns, and reactive updates.
:::{/card}

:::{card} UI and Extensions
:icon: wrench
:link: /chirp/docs/build-apps/ui-extensions/
Shells, accessibility, Alpine, chirp-ui, islands, and tools.
:::{/card}

:::{card} Request Pipeline
:icon: settings
:link: /chirp/docs/build-apps/request-pipeline/
Middleware for CORS, static files, sessions, auth, CSRF, and custom pipelines.
:::{/card}

:::{/cards}
