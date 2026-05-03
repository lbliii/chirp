---
title: Testing
description: TestClient, fragment assertions, SSE testing, and executable hypermedia checks
draft: false
weight: 20
lang: en
type: doc
tags: [testing, test-client, assertions, contracts]
keywords: [testing, test-client, assertions, fragments, sse, pytest]
category: guide
icon: check-circle

cascade:
  type: doc
---

Use this section to exercise the same request, return negotiation, fragment,
and SSE paths your app uses in production.

:::{cards}
:columns: 2
:gap: medium

:::{card} Test Client
:icon: terminal
:link: /chirp/docs/quality/testing/test-client/
:description: TestClient with async context manager
Make requests against your app without a running server.
:::{/card}

:::{card} Assertions
:icon: check
:link: /chirp/docs/quality/testing/assertions/
:description: Fragment and SSE assertion helpers
Specialized assertions for htmx fragment and SSE testing.
:::{/card}

:::{/cards}
