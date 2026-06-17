---
title: Pages and Navigation
description: Routes, filesystem pages, request handling, and navigation structure
draft: false
weight: 10
lang: en
type: doc
tags: [routing, request, response, pages, navigation]
keywords: [routes, path-params, request, response, methods, trie]
category: guide
icon: git-branch

cascade:
  type: doc
---

How requests reach your handlers and how URLs map to code. Coming from Flask or
Django? Start with [[docs/build-apps/pages-navigation/routes|Routes]] for
decorator-based registration, or
[[docs/build-apps/pages-navigation/filesystem-routing|Filesystem Routing]] to map
a `pages/` directory straight onto URLs. Already building? Jump to
[[docs/build-apps/pages-navigation/request-response|Request & Response]] for the
immutable request and chainable response API.

:::{cards}
:columns: 2
:gap: medium

:::{card} Routes
:icon: map
:link: /chirp/docs/build-apps/pages-navigation/routes/
:description: Route registration and path parameters
Decorators, methods, typed parameters, and catch-all routes.
:::{/card}

:::{card} Filesystem Routing
:icon: folder
:link: /chirp/docs/build-apps/pages-navigation/filesystem-routing/
:description: Route discovery from the pages/ directory
Layout nesting, context cascade, and co-located handlers.
:::{/card}

:::{card} Route Directory
:icon: tree-structure
:link: /chirp/docs/build-apps/pages-navigation/route-directory/
:description: `_meta.py`, `_context.py`, `_actions.py`
Sections, shell context, route validation, and filesystem app conventions.
:::{/card}

:::{card} Request & Response
:icon: workflow
:link: /chirp/docs/build-apps/pages-navigation/request-response/
:description: Immutable Request, chainable Response
The frozen request object and the .with_*() response API.
:::{/card}

:::{card} Mounting
:icon: layers
:link: /chirp/docs/build-apps/pages-navigation/mounting/
:description: Compose sub-apps into one route tree
Mount reusable Chirp apps without leaving orphan registries behind.
:::{/card}

:::{/cards}
