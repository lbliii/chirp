---
title: Render HTML Fragments
description: Templates, named blocks, Page, Fragment, OOB swaps, and kida integration
draft: false
weight: 20
lang: en
type: doc
tags: [templates, kida, rendering, fragments, oob]
keywords: [templates, kida, rendering, fragments, page, oob, filters]
category: guide
icon: layers

cascade:
  type: doc
---

:::{cards}
:columns: 2
:gap: medium

Use this section when one template needs to serve full pages, htmx fragments,
OOB updates, Suspense blocks, and SSE payloads.

:::{card} Rendering
:icon: monitor
:link: /chirp/docs/templates/rendering/
:description: Template rendering and context passing
How Template works with kida under the hood.
:::{/card}

:::{card} Fragments
:icon: file-code
:link: /chirp/docs/templates/fragments/
:description: Fragment, Page, and OOB rendering
Render named blocks independently for htmx.
:::{/card}

:::{card} Layout Patterns
:icon: sidebar
:link: /chirp/docs/templates/layout-patterns/
:description: Block-heavy layouts, boost pattern, outer vs inner
When to use block, include, and call.
:::{/card}

:::{card} Filters
:icon: filter
:link: /chirp/docs/templates/filters/
:description: Custom template filters and globals
Register filters and globals on your app.
:::{/card}

:::{card} Kida Integration
:icon: puzzle
:link: /chirp/docs/templates/kida-integration/
:description: AST-driven OOB discovery and regions
How Chirp uses template_metadata() for block validation.
:::{/card}

:::{/cards}
