---
title: Quality and Operations
description: Contract checks, testing, debugging, deployment, and production operations for Chirp apps
draft: false
weight: 20
lang: en
type: doc
tags: [quality, contracts, testing, deployment, operations]
keywords: [chirp, app check, tests, deployment, pounce, operations]
category: guide
icon: check-circle

cascade:
  type: doc
---

Use this section when you need confidence that the server-rendered UI is wired
correctly and will keep working in production.

:::{cards}
:columns: 2
:gap: medium

:::{card} Contracts and Debugging
:icon: shield
:link: /chirp/docs/quality/contracts-debugging/
`app.check`, `chirp check`, DevTools, debug headers, route contracts, and swap failure modes.
:::{/card}

:::{card} Testing
:icon: check
:link: /chirp/docs/quality/testing/
`TestClient`, fragment assertions, SSE testing, and executable hypermedia checks.
:::{/card}

:::{card} Deployment
:icon: server
:link: /chirp/docs/quality/deployment/
Production deployment, Pounce, Docker, Kubernetes, metrics, and runtime config.
:::{/card}

:::{/cards}
