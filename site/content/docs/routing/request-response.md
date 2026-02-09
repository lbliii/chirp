---
title: Request & Response
description: The immutable Request and chainable Response API
draft: false
weight: 20
lang: en
type: doc
tags: [request, response, http, headers, cookies]
keywords: [request, response, headers, cookies, query, body, json, form, chainable]
category: guide
---

## Request

`Request` is a frozen dataclass. From the handler's perspective, received data doesn't change. The object is honest about that.

```python
@app.route("/search")
async def search(request: Request):
    q = request.query.get("q", "")
    lang = request.headers.get("Accept-Language", "en")
    session = request.cookies.get("session_id")
    return Template("search.html", q=q)
```

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `method` | `str` | HTTP method (`GET`, `POST`, etc.) |
| `path` | `str` | Request path (`/search`) |
| `query` | `QueryParams` | Query string parameters |
| `headers` | `Headers` | Immutable request headers |
| `cookies` | `dict[str, str]` | Parsed cookies |
| `content_type` | `str \| None` | Content-Type header value |

### Async Body Access

The request body is accessed asynchronously (it may not have arrived yet):

```python
body_bytes = await request.body()    # Raw bytes
text = await request.text()          # Decoded string
data = await request.json()          # Parsed JSON (dict)
form = await request.form()          # Parsed form data
```

```python
# Streaming the body in chunks
async for chunk in request.stream():
    process(chunk)
```

### htmx Detection

The request knows whether it came from htmx:

```python
request.is_fragment         # True if HX-Request header present
request.htmx_target         # HX-Target value (e.g., "#results")
request.htmx_trigger        # HX-Trigger value
request.is_history_restore  # True if htmx history restore
```

### QueryParams and Headers

Both `QueryParams` and `Headers` implement the `MultiValueMapping` protocol -- they can have multiple values for the same key:

```python
# Single value (first match)
q = request.query.get("q", "")

# All values for a key
tags = request.query.get_all("tag")  # ["python", "web"]

# Check existence
if "q" in request.query:
    ...
```

## Response

Responses are built through chainable transformations. Each `.with_*()` returns a new `Response`:

```python
return (
    Response("Created")
    .with_status(201)
    .with_header("Location", "/users/42")
    .with_cookie("session", token)
)
```

### Chainable Methods

| Method | Description |
|--------|-------------|
| `.with_status(code)` | Set status code |
| `.with_header(name, value)` | Add a header |
| `.with_headers(dict)` | Add multiple headers |
| `.with_content_type(type)` | Set Content-Type |
| `.with_cookie(name, value, **opts)` | Set a cookie |
| `.without_cookie(name)` | Delete a cookie |

### htmx Response Headers

Chirp provides htmx-specific response methods:

```python
return (
    Response("OK")
    .with_hx_redirect("/dashboard")      # HX-Redirect
    .with_hx_location("/new-page")       # HX-Location
    .with_hx_trigger("item-added")       # HX-Trigger
    .with_hx_trigger_after_settle("refresh-count")  # HX-Trigger-After-Settle
)
```

### Immutable Transformations

Each `.with_*()` call creates a new `Response`. The original is never mutated:

```python
base = Response("OK")
with_header = base.with_header("X-Custom", "value")

# base is unchanged
# with_header is a new Response with the added header
```

This makes responses safe to build in middleware pipelines without accidental mutation.

## Redirect

A convenience for 302 redirects:

```python
from chirp import Redirect

@app.route("/old")
def old():
    return Redirect("/new")
```

## Next Steps

- [[docs/core-concepts/return-values|Return Values]] -- All return types
- [[docs/middleware/overview|Middleware]] -- Intercept and transform responses
- [[docs/templates/fragments|Fragments]] -- Fragment-aware request handling
