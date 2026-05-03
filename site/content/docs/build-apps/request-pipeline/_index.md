---
title: Request Pipeline
description: Middleware for CORS, static files, sessions, auth, CSRF, security headers, and custom request pipelines
draft: false
weight: 60
lang: en
type: doc
tags: [middleware, pipeline, protocol, requests]
keywords: [middleware, cors, static, sessions, auth, csrf, protocol]
category: guide
icon: settings

cascade:
  type: doc
---

Use this section when behavior belongs around route handlers rather than inside
them: security headers, sessions, CSRF, static files, CORS, auth, and custom
pipeline logic.

:::{cards}
:columns: 2
:gap: medium

:::{card} Overview
:icon: layers
:link: /chirp/docs/build-apps/request-pipeline/overview/
:description: Protocol definition and pipeline execution
How middleware works -- no base class, no inheritance.
:::{/card}

:::{card} Built-in Middleware
:icon: package
:link: /chirp/docs/build-apps/request-pipeline/builtin/
:description: CORS, StaticFiles, Sessions, Auth, CSRF
Middleware that ships with Chirp.
:::{/card}

:::{card} Custom Middleware
:icon: code
:link: /chirp/docs/build-apps/request-pipeline/custom/
:description: Writing your own middleware
Functions, classes, and real-world patterns.
:::{/card}

:::{card} RenderPlan Middleware
:icon: eye
:link: /chirp/docs/build-apps/request-pipeline/render-plan/
:description: Inspect rendering decisions from middleware
Read-only access to the frozen RenderPlan for analytics, caching, and debugging.
:::{/card}

:::{/cards}
