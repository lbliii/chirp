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

:::{cards}
:columns: 2
:gap: medium

Build the paths users can visit, the page directories that serve them, and the
navigation helpers that keep URLs and route metadata aligned.

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
:icon: file-tree
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
:icon: combine
:link: /chirp/docs/build-apps/pages-navigation/mounting/
:description: Compose sub-apps into one route tree
Mount reusable Chirp apps without leaving orphan registries behind.
:::{/card}

:::{/cards}
