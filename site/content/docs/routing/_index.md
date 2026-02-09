---
title: Routing
description: Routes, path parameters, request, and response
draft: false
weight: 40
lang: en
type: doc
tags: [routing, request, response]
keywords: [routes, path-params, request, response, methods, trie]
category: guide
icon: git-branch

cascade:
  type: doc
---

:::{cards}
:columns: 2
:gap: medium

:::{card} Routes
:icon: map
:link: ./routes
:description: Route registration and path parameters
Decorators, methods, typed parameters, and catch-all routes.
:::{/card}

:::{card} Request & Response
:icon: arrow-right-left
:link: ./request-response
:description: Immutable Request, chainable Response
The frozen request object and the .with_*() response API.
:::{/card}

:::{/cards}
