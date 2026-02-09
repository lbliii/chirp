---
title: Testing
description: Test client, fragment assertions, and SSE testing
draft: false
weight: 80
lang: en
type: doc
tags: [testing, test-client, assertions]
keywords: [testing, test-client, assertions, fragments, sse, pytest]
category: guide
icon: check-circle

cascade:
  type: doc
---

:::{cards}
:columns: 2
:gap: medium

:::{card} Test Client
:icon: terminal
:link: ./test-client
:description: TestClient with async context manager
Make requests against your app without a running server.
:::{/card}

:::{card} Assertions
:icon: check
:link: ./assertions
:description: Fragment and SSE assertion helpers
Specialized assertions for htmx fragment and SSE testing.
:::{/card}

:::{/cards}
