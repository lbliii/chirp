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

Middleware is code that runs *around* every route handler — for cross-cutting
behavior like sessions, CSRF, security headers, static files, CORS, and auth.
Use this section when something belongs around a handler rather than inside it.
Chirp middleware is just a function that matches a Protocol: no base class, no
inheritance.

New here? Start with **Built-in Middleware** to wire the
[secure-by-default stack](/chirp/docs/quality/deployment/auth-hardening/)
(sessions, CSRF, and security headers). Reach for **Custom Middleware** when you
need your own.

:::{child-cards}
:::
