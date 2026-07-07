---
title: Routes
description: Route registration, methods, and path parameters
draft: false
weight: 10
lang: en
type: doc
tags: [routing, routes, decorators, path-params]
keywords: [route, decorator, methods, get, post, path, parameters, trie]
category: guide
---

A route connects a URL to a handler — a function that returns a value Chirp turns into a response. You register one with the `@app.route()` decorator.

Reach for explicit `@app.route()` when you want routing in code. For convention-based routing discovered from a `pages/` directory, see [[docs/build-apps/pages-navigation/filesystem-routing|filesystem routing]] instead.

## Route Registration

Register routes with the `@app.route()` decorator:

```python
@app.route("/")
def index():
    return "Hello, World!"

@app.route("/about")
def about():
    return Template("about.html")
```

Routes are registered during the setup phase. At [[docs/about/core-concepts/app-lifecycle|freeze time]], the route table compiles into an immutable trie-based structure for fast matching.

## HTTP Methods

By default, routes accept `GET` requests. Specify methods explicitly:

```python
@app.route("/users", methods=["GET"])
def list_users():
    return Template("users.html", users=get_all_users())

@app.route("/users", methods=["POST"])
async def create_user(request: Request):
    data = await request.json()
    user = create(data)
    return Response(body=b"Created").with_status(201)

@app.route("/users/{id:int}", methods=["GET", "DELETE"])
async def user(request: Request, id: int):
    if request.method == "DELETE":
        delete_user(id)
        return Response(body=b"Deleted")
    return Template("user.html", user=get_user(id))
```

:::{tip}
If a request matches a path but not the method, Chirp returns `405 Method Not Allowed` with an `Allow` header listing the valid methods — you don't write that fallback yourself.
:::

### HEAD requests

Every `GET` route also answers `HEAD`. Chirp selects the same handler and keeps
`request.method == "HEAD"`, so middleware and handlers can inspect the real
method while returning the same representation metadata as `GET`. The HTTP
server sends the resulting status and headers, including the `Content-Length`
the `GET` body would have, but sends zero body bytes.

Register an explicit `HEAD` route only when its metadata needs different
application logic. It takes precedence over the automatic `GET` fallback:

```python
@app.route("/report", methods=["GET"])
def report():
    return Page("report.html", "report_body")

@app.route("/report", methods=["HEAD"])
def report_metadata():
    return Response("").with_header("X-Report-State", "building")
```

A route allowing `GET` advertises both `GET` and `HEAD` in a `405` response
`Allow` header. Other methods remain exact matches. Built-in `/health` and
`/ready` probes follow the same metadata-without-body wire behavior, making
them safe for uptime monitors and deployment probes.

!!! note "Compatibility"
    Before Chirp 0.4.0, a `GET`-only route rejected `HEAD` with `405 Method Not
    Allowed`. Applications that relied on that rejection should register an
    explicit `HEAD` route and return the response their policy requires.

### Experimental HTTP QUERY routes

Chirp supports the RFC 10008 `QUERY` method on explicitly registered routes.
Declare every request media range the resource understands:

```python
@app.route(
    "/search",
    methods=["QUERY"],
    query_media_types=("application/x-www-form-urlencoded",),
)
async def search(request: Request):
    form = await request.form()
    return Page("search.html", q=form.get("q", ""))
```

`query_media_types` is required for a `QUERY` route and is rejected on routes
that do not include `QUERY`. Chirp validates and normalizes the tuple when the
app freezes. Invalid values, duplicate ranges, unsupported wildcard shapes,
and empty declarations fail startup with the route name and repair guidance.

On the ASGI path, Chirp rejects a missing or malformed `Content-Type` with
`400`, an undeclared media type with `415`, an oversized body with `413` when
the handler reads it, and a negotiated response that cannot satisfy `Accept`
with `406`. QUERY error responses advertise the declared formats through the
RFC 9651 Structured Field `Accept-Query` header. Format parsers and application
validation remain responsible for distinguishing malformed content (`400`)
from a syntactically valid but unprocessable query (`422`). Chirp never sniffs
the body or replaces its declared media type.

This support is experimental and explicit-route-only. QUERY falls through the
fused sync path to ASGI even for a synchronous handler. It does not add a
filesystem `query()` convention, native form transport, a `TestClient.query()`
shortcut, response caching, or a new return type. Use
`TestClient.request("QUERY", ...)` for tests; ordinary HTML needs a separately
designed GET fallback because native forms cannot submit QUERY.

QUERY uses the same typed HTML return pipeline as every other method. A
non-htmx request returning `Page` gets the full document; an htmx request to
the same route gets the selected named block. `Fragment`, OOB, `Stream`, and
`Suspense` keep their existing rendering and fail-loud behavior, including a
hard failure rather than an empty swap when a required block is missing.

With `debug=True`, Chirp DevTools reports QUERY as a safe method and captures
its request and response content types, htmx target, selected block, render
intent, timing, streaming metadata, and errors. Programmatic clients can use
`htmx.ajax("QUERY", path, context)` while declarative QUERY transport remains a
separate compatibility gate.

`CacheMiddleware` still bypasses QUERY by default; an explicit query key
callback enables eligible response snapshots. Chirp's collision-safe key hashes the exact request body, media
metadata, target URI, `Accept`, configured vary headers, and htmx render shape
without exposing raw request content. Building the key retains the body for the
handler and uses the normal request-body limit. By itself, it does not enable cache reads or writes.

To opt in explicitly, manually register `CacheMiddleware` with
`query_key_func=query_cache_key`. The default `None` and
`AppConfig(cache_middleware_enabled=True)` remain GET-only. Only eligible 200
buffered responses are stored; Cookie, Authorization, `Set-Cookie`, streaming,
and SSE paths bypass. Cached QUERY hits preserve response headers and render
intent and re-evaluate ETag/Last-Modified conditions.

See [[docs/build-apps/pages-navigation/http-query|Experimental HTTP QUERY]] for
GET-vs-QUERY guidance, deployment constraints, cache opt-in, compatibility
evidence, and the remaining promotion gates.

#### Discovery, redirects, and validators

For a path with a declared QUERY route, a framework-generated `405` includes
`QUERY` and `OPTIONS` in `Allow` plus the structured `Accept-Query` value.
Chirp also answers `OPTIONS` with a bodyless `204` carrying those headers unless
you registered an explicit `OPTIONS` route, which always wins.

Use existing response headers for retrievable results and equivalent resources:

```python
return (
    Response(rendered_results)
    .with_header("Content-Location", "/results/r_54a59b9f")
    .with_header("Location", "/searches/q_7f83b165")
    .with_header("ETag", 'W/"search-v1"')
)
```

Identifiers are application-owned and must be opaque; never copy sensitive
QUERY content into a temporary URI. Ordinary GET and QUERY `Response` values
share `If-None-Match` and `If-Modified-Since` evaluation when the application
supplies `ETag` or `Last-Modified`, producing a bodyless `304` on a match.

`Redirect` also remains the only redirect primitive. Chirp preserves `301`,
`302`, `307`, and `308` so an RFC-compliant client can repeat QUERY, while
`303` hands the client off to GET. Test the actual client in your deployment;
when method retention is critical, prefer `307` or `308` because common client
compatibility around custom methods and `301`/`302` varies.

Range behavior is unchanged: range-capable responses such as the existing file
sender retain GET semantics for QUERY, while generic HTML responses make no
byte-range promise. Query formats should generally expose their own paging or
limit controls instead.

## Path Parameters

Dynamic segments are defined with curly braces:

```python
@app.route("/users/{id}")
def user(id: str):
    return f"User: {id}"
```

### Type Conversions

Add a type suffix to auto-convert parameters:

```python
@app.route("/users/{id:int}")
def user(id: int):          # id is an int, not a str
    return get_user(id)

@app.route("/price/{amount:float}")
def price(amount: float):   # amount is a float
    return f"${amount:.2f}"
```

Supported converters:

:::{list-table}
:header-rows: 1

* - Converter
  - Matches
  - Example
* - `str`
  - (default) any chars except `/`
  - `/users/{name}`
* - `int`
  - digits only
  - `/users/{id:int}`
* - `float`
  - digits with an optional decimal
  - `/price/{amount:float}`
* - `path`
  - any chars, including `/`
  - `/files/{filepath:path}`
:::

Parameter names must be valid Python identifiers, converters must be one of the supported names above, and routes use Chirp's `{param}` syntax rather than Flask-style `<param>`. Routes that differ only by parameter name, such as `/users/{id}` and `/users/{name}`, are duplicate route shapes and are rejected.

`url_for()` validates supplied path values against the same converter rules, so `url_for("users.detail", id="alice")` fails for `/users/{id:int}` instead of generating a URL the router cannot match.

### Catch-All Routes

Use `{name:path}` to match the rest of the URL:

```python
from pathlib import Path

@app.route("/files/{filepath:path}")
def serve_file(filepath: str):          # filepath can contain slashes
    return FileResponse(Path("uploads") / filepath)
```

`FileResponse` streams the file from disk with conditional-GET and `Range` support — you don't read it into memory yourself.

:::{warning}
A `path` converter must be the final segment — it consumes the rest of the URL. Putting anything after it raises `ConfigurationError` at registration.
:::

## Handler Signature Introspection

Chirp inspects your handler's signature to inject the right arguments:

```python
# No arguments -- simplest case
@app.route("/")
def index():
    return "Hello"

# Request only
@app.route("/search")
def search(request: Request):
    q = request.query.get("q", "")
    return Template("search.html", q=q)

# Path parameters only
@app.route("/users/{id:int}")
def user(id: int):
    return get_user(id)

# Both
@app.route("/users/{id:int}/posts/{slug}")
def user_post(request: Request, id: int, slug: str):
    return Template("post.html", post=get_post(id, slug))

# Extractable dataclasses — from query (GET), form (POST), or JSON body
@app.route("/search")
def search(form: SearchForm):
    return Template("search.html", q=form.q, page=form.page)

# Dependency injection — register a type-keyed factory, then declare it as a param
def get_store() -> DocumentStore:
    return DocumentStore()

app.provide(DocumentStore, get_store)

@app.route("/documents/{id}")
def document(id: str, store: DocumentStore):
    return Template("doc.html", doc=store.get(id))
```

Argument resolution (first match wins):

- **[[docs/build-apps/pages-navigation/request-response|Request]]** — Parameter named `request` or typed as `Request`
- **Path parameters** — From URL match, with type coercion
- **Extractable dataclasses** — Query string (GET), form body (POST), or JSON body. Dataclass fields are populated from request data.
- **Service providers** — Registered via `app.provide(annotation, factory)`. When a parameter's type matches a registered factory, Chirp injects the result.

## Async Handlers

Handlers can be sync or async. Chirp handles both:

```python
@app.route("/sync")
def sync_handler():
    return "Sync"

@app.route("/async")
async def async_handler():
    data = await fetch_data()
    return Template("data.html", data=data)
```

Use async handlers when you need to `await` I/O (database queries, HTTP calls, file reads).

## Error Handlers

Register error handlers by status code or exception type:

```python
@app.error(404)
def not_found(request: Request):
    return Template("errors/404.html", path=request.path)

@app.error(500)
def server_error(request: Request, error: Exception):
    return Template("errors/500.html", error=str(error))

class PaymentRequired(HTTPError):
    """Raised by a handler when the caller has no active subscription."""
    def __init__(self, detail: str = "Subscription required") -> None:
        super().__init__(status=402, detail=detail)

@app.error(PaymentRequired)
def payment_required(request: Request, error: PaymentRequired):
    return Template("errors/payment.html", reason=error.detail)
```

`@app.error()` takes a status code or an **exception type**. Chirp dispatches to the handler when a route raises a matching exception, or when it produces that status. The handler receives the `Request` and, for exception handlers, the raised exception. An `HTTPError` carries its own status, so the returned `Template` is sent with that code. Error handlers use the same [[docs/about/core-concepts/return-values|return-value system]] as route handlers.

:::{note}
Register an exception type only if your code actually `raise`s it. Chirp's own return types — including `ValidationError`, which you *return* to send a 422 form fragment — are values, not exceptions you catch. See [[docs/about/core-concepts/return-values|return values]] for the full set.
:::

## Route Table

Every route you register lands in one table that Chirp compiles at [[docs/about/core-concepts/app-lifecycle|freeze time]].

:::{note}
At freeze time, routes compile into a trie (prefix tree), so matching is O(path-segments), not O(total-routes) — performance doesn't degrade as you add routes. The compiled table is immutable and shared across worker threads without synchronization (see [[docs/about/thread-safety|thread safety]]).
:::

::::{dropdown} Advanced: how contract checks validate route URLs in templates
When `chirp check <app>` [[docs/quality/contracts-debugging/route-contract|validates templates]], it extracts `hx-get`, `hx-post`, `hx-put`, `hx-delete`, `hx-patch`, `action`, and route-bearing macro arguments such as `confirm_url`, then verifies method + path against the route table.

Literal URLs are checked against route converter rules, so `/users/alice` does not satisfy `/users/{id:int}`. Dynamic URLs (built with Kida's `~` or `{{ }}`) are skipped; only literal URLs are validated. Use `~` or `{{ var }}` for path parameters — both work at render time and are correctly treated as dynamic by the checker.

`confirm_url` defaults to `POST` unless a companion `confirm_method` is present, which lets dialog-style component APIs participate in the same route validation as raw htmx attributes.

Legacy component-style `action="update-thing"` values are no longer treated as route URLs. Chirp emits a warning instead of a false route error so you can migrate older macros to literal URLs or explicit htmx attributes over time.

The checker also validates selector-bearing htmx attributes (`hx-target`, `hx-select`, `hx-include`, and similar) for obvious syntax mistakes and unknown static `#id` targets.
::::{/dropdown}

:::{note} See also
- [[docs/build-apps/pages-navigation/filesystem-routing|Filesystem Routing]] — Discover routes from a `pages/` directory
- [[docs/build-apps/pages-navigation/request-response|Request & Response]] — The immutable request and chainable response
- [[docs/build-apps/request-pipeline/overview|Middleware]] — Intercept requests before they reach handlers
- [[docs/build-apps/html-fragments/fragments|Fragments]] — Return fragments from route handlers
:::
