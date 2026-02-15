---
title: Examples
description: Full-featured Chirp applications showcasing the framework
draft: false
weight: 105
lang: en
type: doc
tags: [examples, demos, rag, sse, streaming]
keywords: [examples, demos, rag, sse, streaming, fragments]
category: tutorial
icon: box

cascade:
  type: doc
---

:::{cards}
:columns: 2
:gap: medium

:::{card} RAG Demo
:icon: message-circle
:link: ./rag-demo
:description: Streaming AI Q&A with cited sources, dual-model comparison, and zero client JS
The flagship Chirp example: fragments, SSE, event delegation, and free-threading.
:::{/card}

:::{card} Production Stack
:icon: shield
:link: ../../examples/production/
:description: SecurityHeadersMiddleware, SessionMiddleware, CSRFMiddleware, contact form
Production-ready security stack with CSRF protection and security header tests.
:::{/card}

:::{card} API
:icon: code
:link: ../../examples/api/
:description: Pure JSON REST API — dict returns, path params, request.json(), CORS
API-only Chirp app with CRUD, no HTML.
:::{/card}

:::{/cards}
