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

Every handler receives a `Request` and returns a value that Chirp turns into a
response. `Request` is a frozen, read-only snapshot of the incoming HTTP request
-- method, path, headers, cookies, query string, and an async-readable body.
When you need to control the raw response (status, headers, cookies, redirects),
you build a `Response` through chainable `.with_*()` transformations; each call
returns a new immutable copy.

Most handlers never construct a `Response` directly. They return a
[[docs/about/core-concepts/return-values|return type]] like `Template` or
`Fragment` and let Chirp negotiate the response. Reach for `Request` and
`Response` when you need the raw HTTP details.

## Request

`Request` is a frozen dataclass -- a snapshot of what arrived. The data does not
change under you mid-handler, and the object is honest about that.

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

### Async body access

The body is read asynchronously -- it may not have arrived yet. Pick the access
method that matches your content type; they all read the same underlying body.

::::{code-tabs}
:sync: body

```python title="Raw bytes"
async def upload(request: Request):
    body_bytes = await request.body()
```

```python title="Decoded text"
async def note(request: Request):
    text = await request.text()
```

```python title="Parsed JSON"
async def api(request: Request):
    data = await request.json()
```

```python title="Form data"
async def submit(request: Request):
    form = await request.form()
```

```python title="Stream chunks"
async def ingest(request: Request):
    async for chunk in request.stream():
        process(chunk)
```

::::

### htmx detection

When a request comes from htmx, you can branch on it. The richest surface is the
typed `request.htmx` namespace ([`HtmxDetails`](https://github.com/lbliii/chirp/blob/main/src/chirp/http/request.py)),
which is truthy when the `HX-Request` header is present:

```python
@app.route("/results")
def results(request: Request):
    if request.htmx:                 # any htmx request
        target = request.htmx.target       # raw: "#results" or "div#results"
        target_id = request.htmx.target_id # canonical: "results"
        source_id = request.htmx.source_id # htmx 4 HX-Source id
        trigger = request.htmx.trigger     # htmx 2 id, or source_id fallback
    ...
```

For most handlers you do not need to branch by hand at all -- return a
[[docs/build-apps/html-fragments/fragments|Page]] and Chirp negotiates a fragment
for htmx and a full page for browsers. Branch manually only when the two paths
truly differ.

Two convenience properties cover the common questions:

| Property | True when |
|----------|-----------|
| `request.is_htmx` | Any htmx request (`HX-Request` present) |
| `request.is_narrow_fragment` | A narrow swap -- excludes boosted navigations, history restores, and htmx 4 body-level `full` requests |
| `request.htmx.request_type` | Valid htmx 4 `HX-Request-Type` (`"full"` / `"partial"`), otherwise `None` |

:::{deprecated} request.is_fragment
`request.is_fragment` is ambiguous for boosted navigations and emits a
`DeprecationWarning`. Use `request.is_htmx` (any htmx request) or
`request.is_narrow_fragment` (narrow swap only).
:::

:::{tip}
The flat `request.htmx_target` / `request.htmx_trigger` properties are
convenience shims that delegate to `request.htmx`. Prefer the typed namespace --
`request.htmx.target`, `request.htmx.boosted`, `request.htmx.history_restore`,
`request.htmx.target_id` (the bare DOM id used throughout the framework's
request pipeline), and `request.htmx.source_id` / `source_tag` for htmx 4.
Htmx 4 removed `HX-Trigger-Name`; if a handler needs an application name rather
than a stable source id, send an explicit application header with `hx-headers`
and read it from `request.headers`.
:::

### QueryParams and Headers

Both `QueryParams` and `Headers` implement the `MultiValueMapping` protocol --
the same key can carry multiple values:

```python
# First value
q = request.query.get("q", "")

# All values for a key
tags = request.query.get_list("tag")   # ["python", "web"]

# Typed coercion (None if missing or unparseable)
page = request.query.get_int("page", 1)
debug = request.query.get_bool("debug", False)

# Existence
if "q" in request.query:
    ...
```

## Response

Responses are built through chainable transformations. Each `.with_*()` returns
a new `Response`:

```python
return (
    Response("Created")
    .with_status(201)
    .with_header("Location", "/users/42")
    .with_cookie("session", token)
)
```

`with_hx_trigger_after_settle()` and `with_hx_trigger_after_swap()` are htmx 2
and generic wire helpers. Htmx 4 removed both response headers. When the exact
preview tier serves an htmx request containing either header, Chirp rejects the
response before send with the unsupported header, helper, selected version,
and lifecycle migration.

For htmx 4, render the event payload into the same target block as escaped
`data-*` attributes. External application JavaScript reads that marker from
the target's `htmx:before:settle` (old after-swap intent) or
`htmx:after:settle` (old after-settle intent) event. Do not map either header
to receipt-phase `HX-Trigger` or request-level `htmx:after:swap`; both change
the timing contract.

### Chainable methods

| Method | Description |
|--------|-------------|
| `.with_status(code)` | Set status code |
| `.with_header(name, value)` | Add a header |
| `.with_headers(dict)` | Add multiple headers |
| `.with_content_type(type)` | Set Content-Type |
| `.with_cookie(name, value, **opts)` | Set a cookie |
| `.without_cookie(name)` | Delete a cookie |

`.with_header()` and `.with_headers()` *append* -- they do not replace an
existing header of the same name.

:::{dropdown} Why responses are immutable
Each `.with_*()` call creates a new `Response`; the original is never mutated:

```python
base = Response("OK")
with_header = base.with_header("X-Custom", "value")

# base is unchanged
# with_header is a new Response with the added header
```

Immutability makes responses safe to pass through
[[docs/build-apps/request-pipeline/_index|response-transforming middleware]]
without one layer accidentally clobbering another's headers.
:::

### htmx response headers

Chirp provides htmx-specific response methods:

```python
return (
    Response("OK")
    .with_hx_location("/new-page")                  # HX-Location
    .with_hx_trigger("item-added")                  # HX-Trigger
    .with_hx_trigger_after_settle("refresh-count")  # htmx 2/generic only
)
```

## Redirects

`Redirect` is the plain HTTP redirect, defaulting to status `302`:

```python
from chirp import Redirect

@app.route("/old")
def old():
    return Redirect("/new")
```

For a redirect that must work for both htmx and plain requests, use
`hx_redirect()` (status `303` by default):

```python
from chirp import hx_redirect

@app.route("/items/{id:int}/archive", methods=["POST"])
def archive_item(id: int):
    archive(id)
    return hx_redirect("/items")
```

:::{danger} Never set Location and HX-Redirect by hand together
An htmx request runs over XHR, which follows a `Location` header *before* it ever
reads `HX-Redirect` -- so a response carrying both silently does the wrong thing.
`hx_redirect()` exists to solve exactly this: the negotiation layer strips the
conflicting header per client. htmx requests receive `200` with `HX-Redirect`
only (no `Location`); non-htmx requests receive the HTTP redirect via `Location`
only. Compose the two headers manually and you reintroduce the footgun.
:::

:::{tip}
For form POST success paths, prefer `FormAction` or `MutationResult` over
`hx_redirect()` -- they apply the same negotiation automatically. See
[[docs/build-apps/forms-data/forms-validation|form POST success paths]].
:::

:::{note} See also
- [[docs/about/core-concepts/return-values|Return Values]] -- every type a handler can return, and how Chirp negotiates each
- [[docs/build-apps/html-fragments/fragments|Fragments]] -- fragment-aware request handling and `Page` auto-negotiation
- [[docs/build-apps/request-pipeline/_index|Middleware]] -- intercept and transform responses
:::

:::{related}
:::
