---
title: Test Client
description: Make requests against your app without a running server
draft: false
weight: 10
lang: en
type: doc
tags: [testing, test-client, httpx]
keywords: [test-client, testing, httpx, async, requests, pytest]
category: guide
---

## Overview

`TestClient` sends requests through your app's ASGI handler directly -- no network, no running server. It uses the same `Request` and `Response` types as production, so there is no translation layer to introduce bugs.

:::{note}
Requires the `testing` extra: `pip install bengal-chirp[testing]`.
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

```python
async def test_methods():
    async with TestClient(app) as client:
        # GET
        response = await client.get("/users")
        assert response.status == 200

        # POST with JSON
        response = await client.post("/users", json={"name": "Alice"})
        assert response.status == 201

        # POST with form data
        response = await client.post("/login", data={"username": "alice", "password": "secret"})

        # PUT
        response = await client.put("/users/1", json={"name": "Alice Updated"})

        # DELETE
        response = await client.delete("/users/1")
        assert response.status == 200
```

## Custom Headers

```python
async def test_with_headers():
    async with TestClient(app) as client:
        response = await client.get("/api/data", headers={
            "Authorization": "Bearer token123",
            "Accept": "application/json",
        })
```

## Fragment Requests

Simulate htmx fragment requests:

```python
async def test_fragment():
    async with TestClient(app) as client:
        # Send with HX-Request header to trigger fragment rendering
        response = await client.get("/search?q=test", headers={
            "HX-Request": "true",
            "HX-Target": "#results",
        })
        assert response.status == 200
        assert "<div id=\"results\">" in response.text
        # Fragment response -- no full page wrapper
        assert "<html>" not in response.text
```

The `TestClient` also provides a convenience method:

```python
async def test_fragment_convenience():
    async with TestClient(app) as client:
        response = await client.fragment("/search?q=test", target="#results")
        assert response.status == 200
```

## Cookies

```python
async def test_session():
    async with TestClient(app) as client:
        # Login sets a cookie
        await client.post("/login", data={"user": "alice", "pass": "secret"})

        # Subsequent requests include the cookie
        response = await client.get("/dashboard")
        assert response.status == 200
        assert "alice" in response.text
```

## Response Properties

| Property | Type | Description |
|----------|------|-------------|
| `status` | `int` | HTTP status code |
| `text` | `str` | Response body as string |
| `json` | `dict` | Parsed JSON body |
| `headers` | `dict` | Response headers |
| `cookies` | `dict` | Response cookies |

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

## Next Steps

- [[docs/testing/assertions|Assertions]] -- Fragment and SSE assertion helpers
- [[docs/templates/fragments|Fragments]] -- How fragments work
- [[docs/streaming/server-sent-events|Server-Sent Events]] -- SSE testing
