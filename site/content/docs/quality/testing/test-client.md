---
title: Test Client
description: Make requests against your app without a running server
draft: false
weight: 10
lang: en
type: doc
tags: [testing, test-client, pytest]
keywords: [test-client, testing, asgi, async, requests, pytest, fragment]
category: guide
---

## Overview

`TestClient` runs requests straight through your app's ASGI handler in-process -- no socket, no running server, no test HTTP layer. It builds the same `Request` and returns the same `Response` your app uses in production, so a passing test exercises the real code path.

Reach for it in pytest to assert status, body, and fragment-vs-full-page rendering. It also runs your startup and per-worker hooks, so apps that open a DB connection or HTTP client in `on_worker_startup` behave exactly as they do in production.

:::{tip}
`TestClient` itself has no extra dependencies -- it drives ASGI directly. The `testing` extra (`pip install bengal-chirp[testing]`) adds only `httpx`; install it when your *app* uses an `httpx` client (e.g. in `on_worker_startup`). The link-crawl helper needs nothing extra, and the browser-smoke helper needs Playwright (`uv sync --group dev --group browser`), not the `testing` extra.
:::

## Basic Usage

```python
from chirp.testing import TestClient

async def test_homepage():
    async with TestClient(app) as client:
        response = await client.get("/")
        assert response.status == 200
        assert "Hello" in response.text
```

The `TestClient` is an async context manager. It handles app startup/shutdown lifecycle automatically.

## HTTP Methods

Every method accepts a `headers=` dict. `post()` also takes `data=` (form-encoded), `json=` (JSON body), or raw `body=` bytes; `put()` and `delete()` take only `headers=` and (for `put`) `body=`.

```python
async def test_methods():
    async with TestClient(app) as client:
        # GET with custom headers
        response = await client.get("/api/data", headers={
            "Authorization": "Bearer token123",
            "Accept": "application/json",
        })
        assert response.status == 200

        # POST with JSON
        response = await client.post("/users", json={"name": "Alice"})
        assert response.status == 201

        # POST with form data
        response = await client.post("/login", data={"username": "alice", "password": "secret"})

        # PUT with a raw body (put() has no json= / data= shortcut)
        import json
        response = await client.put(
            "/users/1",
            body=json.dumps({"name": "Alice Updated"}).encode(),
            headers={"Content-Type": "application/json"},
        )

        # DELETE
        response = await client.delete("/users/1")
        assert response.status == 200
```

## Fragment Requests

To simulate an htmx request, send the `HX-Request` header so your handler renders a [[docs/build-apps/html-fragments/fragments|fragment]] instead of a full page. The `fragment()` convenience method sets that header for you and exposes `target=`, `trigger=`, and `history_restore=`. For htmx 4, pass `source=` and `request_type=`; the latter also defaults `Accept` to `text/html`:

```python
async def test_fragment():
    async with TestClient(app) as client:
        response = await client.fragment("/search?q=test", target="#results")
        assert response.status == 200
        assert '<div id="results">' in response.text

        htmx4 = await client.fragment(
            "/search?q=test",
            target="div#results",
            source="input#search",
            request_type="partial",
        )
        assert htmx4.status == 200
```

Use the [[docs/quality/testing/assertions|fragment and SSE assertions]] (`assert_is_fragment`, `assert_is_full_page`, ...) to check fragment-vs-full-page rendering without hand-writing `<html>` string checks.

## Boosted navigation requests

Boosted shell navigation is not the same request shape as a narrow fragment
swap. Use `boosted()` to send the headers htmx sends for a boosted link:
`HX-Request: true`, `HX-Boosted: true`, and the required `HX-Target` outlet.
Pass the target element ID as htmx sends it in the header, without a CSS `#`.

```python
async def test_boosted_project_navigation():
    async with TestClient(app) as client:
        response = await client.boosted("/projects/apollo", target="main")
        assert response.status == 200
        assert 'id="page-content"' in response.text
```

| Request | Helper | Intended response |
| --- | --- | --- |
| Browser page load | `client.get(...)` | Full page |
| Narrow htmx target | `client.fragment(..., target="results")` | Target block only |
| Htmx 4 narrow target | `client.fragment(..., target="div#results", source="button#go", request_type="partial")` | Target block only |
| Boosted shell outlet | `client.boosted(..., target="main")` | `Page` / mounted-page outlet negotiation |

For shell outlets that use `hx-select`, a negotiated `Page` response can carry
the full shell document with fragment render intent so the browser selects the
declared outlet. A raw `Template` still has full-page intent and is unsafe for a
boosted target. `RouteSmokeCase(mode="boosted")` distinguishes those cases.

## Cookies and sessions

:::{warning}
`TestClient` does **not** keep a cookie jar. A `Set-Cookie` on one response is not automatically sent back on the next request. To test a session flow, read the cookie off the login response and pass it forward yourself:

```python
async def test_session():
    async with TestClient(app) as client:
        login = await client.post("/login", data={"user": "alice", "pass": "secret"})
        cookie = login.cookies[0]  # SetCookie

        response = await client.get(
            "/dashboard",
            headers={"Cookie": f"{cookie.name}={cookie.value}"},
        )
        assert response.status == 200
```
:::

## Response Properties

The returned object is the same `Response` your handlers produce. The fields you assert on most:

| Property | Type | Description |
|----------|------|-------------|
| `status` | `int` | HTTP status code |
| `text` | `str` | Response body as a string |
| `json` | property | Body parsed as JSON; raises `ValueError` on non-JSON |
| `header(name, default=None)` | method | First matching header value (case-insensitive) |
| `headers` | `tuple[tuple[str, str], ...]` | Raw header pairs |
| `cookies` | `tuple[SetCookie, ...]` | `Set-Cookie` values on the response |

Read a single header with the `header()` method rather than indexing `headers`:

```python
assert response.header("Content-Type") == "application/json"
```

## Using with pytest

```python
import pytest
from myapp import app

@pytest.fixture
async def client():
    async with TestClient(app) as c:
        yield c

async def test_homepage(client):
    response = await client.get("/")
    assert response.status == 200
```

:::{dropdown} Smoke-test a whole route set
When you want one test to prove a set of routes still renders (in CI, after a
refactor), `assert_route_smoke` runs each route through the client and checks its
render mode -- full page, narrow fragment, boosted outlet, status-only, or
`both` (full page plus narrow fragment):

```python
from chirp.testing import RouteSmokeCase, TestClient, assert_route_smoke

async def test_showcase_routes(app):
    async with TestClient(app) as client:
        await assert_route_smoke(client, [
            RouteSmokeCase("/", mode="full_page", name="home"),
            RouteSmokeCase("/search?q=chirp", mode="fragment",
                           block="results", target="results"),
            RouteSmokeCase("/projects/apollo", mode="boosted",
                           block="page_root", target="main"),
            RouteSmokeCase("/health", mode="status"),
        ])
```

Failures include the path, request intent, observed response shape, status, and
any supplied target, route name, template, or block. A full-page `Template`
returned to a boosted shell target therefore identifies the route and target
instead of silently passing as a valid outlet response.
:::

:::{note} See also
- [[docs/quality/testing/assertions|Assertions]] -- fragment, OOB, and SSE assertion helpers
- [[docs/build-apps/html-fragments/fragments|Fragments]] -- how fragment rendering works
- [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]] -- testing SSE endpoints with `client.sse()`
- [[docs/quality/testing/_index|Testing overview]] -- the full testing toolkit
:::
