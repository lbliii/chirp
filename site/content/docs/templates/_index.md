---
title: Templates
description: Rendering, fragments, and template integration with kida
draft: false
weight: 30
lang: en
type: doc
tags: [templates, kida, rendering, fragments]
keywords: [templates, kida, rendering, fragments, page, oob, filters]
category: guide
icon: layers

cascade:
  type: doc
---

:::{cards}
:columns: 2
:gap: medium

:::{card} Rendering
:icon: monitor
:link: ./rendering
:description: Template rendering and context passing
How Template works with kida under the hood.
:::{/card}

:::{card} Fragments
:icon: scissors
:link: ./fragments
:description: Fragment, Page, and OOB rendering
Render named blocks independently for htmx.
:::{/card}

:::{card} Layout Patterns
:icon: layout
:link: ./layout-patterns
:description: Block-heavy layouts, boost pattern, outer vs inner
When to use block, include, and call.
:::{/card}

:::{card} Filters
:icon: filter
:link: ./filters
:description: Custom template filters and globals
Register filters and globals on your app.
:::{/card}

:::{/cards}
