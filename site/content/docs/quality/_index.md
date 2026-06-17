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

You have an app working, and now you need to ship it and keep it correct. This
section is for the operator and the builder mid-project: it covers the contracts
that catch broken hypermedia wiring before users do, how to test fragment and
SSE responses, and how to deploy to production. New here? Start with
[[docs/quality/contracts-debugging/_index|Contracts and Debugging]] to learn how
`app.check()` fails loud at startup, then [[docs/quality/testing/_index|Testing]],
then [[docs/quality/deployment/_index|Deployment]] when you are ready to ship.

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
