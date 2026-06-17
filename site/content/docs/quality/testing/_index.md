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

Test your Chirp app the way it actually runs — drive real requests through the
ASGI handler, then assert on the fragment, OOB, and SSE responses that come
back. Start with the [[docs/quality/testing/test-client|TestClient]] to make
requests without a running server, then reach for the
[[docs/quality/testing/assertions|fragment and SSE assertions]] to check the
hypermedia your handlers return.

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
:description: Fragment, OOB, and SSE assertion helpers
Check the fragments, out-of-band swaps, htmx headers, and SSE wiring your handlers return.
:::{/card}

:::{/cards}

:::{note} See also
- [[docs/quality/contracts-debugging/categories|Contract categories]] — `app.check()` catches hypermedia-contract breakage at startup; testing catches it at request time
:::
