---
title: Assertions
description: Fragment and SSE assertion helpers
draft: false
weight: 20
lang: en
type: doc
tags: [testing, assertions, fragments, sse]
keywords: [assertions, fragment, sse, testing, htmx, helpers]
category: guide
---

## Fragment Assertions

Chirp provides specialized assertion helpers for testing fragment responses:

```python
from chirp.testing import TestClient
from chirp.testing.assertions import (
    assert_is_fragment,
    assert_fragment_contains,
    assert_fragment_not_contains,
    assert_is_error_fragment,
)
```

### assert_is_fragment

Verify that a response is a fragment (not a full page):

```python
async def test_search_returns_fragment():
    async with TestClient(app) as client:
        response = await client.get("/search?q=test", headers={"HX-Request": "true"})
        assert_is_fragment(response)
```

This checks that the response does not contain `<html>` or `<body>` tags -- it is a partial HTML snippet, not a full page.

### assert_fragment_contains

Check that a fragment response contains specific content:

```python
async def test_search_results():
    async with TestClient(app) as client:
        response = await client.get("/search?q=apple", headers={"HX-Request": "true"})
        assert_fragment_contains(response, "apple")
        assert_fragment_contains(response, '<div id="results">')
```

### assert_fragment_not_contains

Verify that a fragment does not contain certain content:

```python
async def test_search_excludes():
    async with TestClient(app) as client:
        response = await client.get("/search?q=apple", headers={"HX-Request": "true"})
        assert_fragment_not_contains(response, "banana")
```

### assert_is_error_fragment

Check that a fragment is an error fragment (contains the error CSS class):

```python
async def test_error_fragment():
    async with TestClient(app) as client:
        response = await client.get("/missing", headers={"HX-Request": "true"})
        assert_is_error_fragment(response)
```

## SSE Testing

Test Server-Sent Event endpoints with `TestClient.sse()`:

```python
from chirp.testing import TestClient

async def test_notifications():
    async with TestClient(app) as client:
        result = await client.sse("/notifications", max_events=3)

        # Check event count
        assert len(result.events) == 3

        # Check individual events
        assert "notification" in result.events[0].data
```

### SSETestResult

The `sse()` method returns an `SSETestResult` with collected events:

| Property | Type | Description |
|----------|------|-------------|
| `events` | `list[SSEEvent]` | Collected SSE events |

Each event has:

| Property | Type | Description |
|----------|------|-------------|
| `data` | `str` | Event data payload |
| `event` | `str \| None` | Event type |
| `id` | `str \| None` | Event ID |
| `retry` | `int \| None` | Retry interval |

### Controlling Collection

```python
# Collect up to 5 events
result = await client.sse("/events", max_events=5)

# Collect for 2 seconds, then disconnect
result = await client.sse("/events", disconnect_after=2.0)
```

### Testing Event Types

```python
async def test_typed_events():
    async with TestClient(app) as client:
        result = await client.sse("/events", max_events=5)

        # Filter by event type
        user_events = [e for e in result.events if e.event == "user-join"]
        assert len(user_events) >= 1

        # Check event data
        for event in result.events:
            assert event.data  # Not empty
```

## Combining Assertions

A complete test for an htmx-powered search feature:

```python
async def test_search_flow():
    async with TestClient(app) as client:
        # Full page load
        response = await client.get("/search")
        assert response.status == 200
        assert "<html>" in response.text  # Full page

        # htmx fragment request
        response = await client.get("/search?q=python", headers={
            "HX-Request": "true",
            "HX-Target": "#results",
        })
        assert response.status == 200
        assert_is_fragment(response)
        assert_fragment_contains(response, "python")
        assert_fragment_not_contains(response, "<html>")
```

## Next Steps

- [[docs/testing/test-client|Test Client]] -- TestClient usage
- [[docs/templates/fragments|Fragments]] -- How fragments work
- [[docs/streaming/server-sent-events|Server-Sent Events]] -- SSE endpoints
