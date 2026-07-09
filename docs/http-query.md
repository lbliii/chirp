# HTTP QUERY: experimental adoption guide

**Status:** Experimental early-adopter support. Stable promotion is not approved.

**Protocol:** [RFC 10008](https://www.rfc-editor.org/rfc/rfc10008.html)

**Chirp contract:** [RFC 009](rfcs/009-http-query.md)

HTTP `QUERY` is a safe, idempotent, body-bearing method for queries whose input
is too structured or large for a practical URI. Chirp supports it on explicit
ASGI routes without adding a JSON response layer, a new return type, or a
second template system. Handlers return the same `Page`, `Fragment`, OOB,
`Stream`, `Suspense`, `ValidationError`, `Response`, and `Redirect` values used
by other methods.

The feature is ready for controlled early-adopter evaluation, not a universal
production claim. Browser, Pounce, Uvicorn, and Nginx proof exists, but clients,
proxies, and CDNs can reject unfamiliar methods independently. Test the exact
deployment path and retain a GET fallback or equivalent GET resource.

## Choose GET by default

| Need | Use |
| --- | --- |
| Bookmarkable, shareable, ordinary search with compact inputs | `GET` |
| Native HTML form and no-JavaScript submission | `GET` |
| Large or structured read-only query whose URI would be awkward | Experimental `QUERY` |
| Requested mutation or action with side effects | `POST`, `PUT`, `PATCH`, or `DELETE` as appropriate |
| Durable identity for a QUERY result | Application-owned equivalent `GET` resource |

A body is not a reason to choose QUERY by itself. The handler must remain safe
and idempotent: it cannot perform a requested mutation, and it must tolerate a
retry or HTTP/3 0-RTT replay where the deployment enables either behavior.

## Declare an explicit route

```python
from chirp import App, Page, Request

app = App()


@app.route(
    "/search",
    methods=["QUERY"],
    query_media_types=("application/x-www-form-urlencoded",),
)
async def search(request: Request) -> Page:
    form = await request.form()
    results = await find_results(form)
    return Page("search.html", "results", results=results)
```

`query_media_types` is mandatory on a QUERY route and invalid on a route that
does not include QUERY. Chirp validates and freezes its RFC 10008 media ranges
at startup. The implementation is explicit-route-only: there is no filesystem
`query()` handler convention and no `AppConfig` feature flag.

Use the generic test-client surface:

```python
response = await client.request(
    "QUERY",
    "/search",
    headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "text/html",
    },
    body=b"category=books&year=2026",
)
```

There is no `TestClient.query()` convenience method. Adding one remains a
separate public-API decision in issue #527.

## Request and response contract

| Condition | Chirp behavior |
| --- | --- |
| Missing or malformed `Content-Type` | `400 Bad Request` |
| Well-formed but undeclared request media type | `415 Unsupported Media Type` plus `Accept-Query` |
| Body exceeds the effective server/framework limit | `413 Payload Too Large` |
| Selected response cannot satisfy `Accept` | `406 Not Acceptable` |
| Format-specific malformed query | Handler/parser returns `400` |
| Valid syntax that cannot be processed | Handler returns `422 Unprocessable Content` |
| Method mismatch on a QUERY-capable path | `405` with `Allow` and `Accept-Query` |
| Implicit discovery | bodyless `204 OPTIONS` with `Allow` and `Accept-Query` |

An explicit application `OPTIONS` route always wins. Chirp never sniffs the
request body or silently changes its declared content type.

QUERY uses the ordinary typed render pipeline. A full request can render the
complete document, while an htmx request can render the named block from the
same Kida template. Missing required blocks still fail loud. `Stream` remains
progressive response HTML, `Suspense` remains shell plus deferred OOB blocks,
and `EventStream` remains post-load SSE.

## Progressive enhancement boundary

Native HTML forms cannot submit QUERY. The unenhanced path must therefore be a
normal GET form or another explicitly designed fallback. Programmatic Fetch
and `htmx.ajax("QUERY", ...)` have browser proof, but Chirp does not yet publish
a declarative `hx-query` attribute or a stable adapter. Issue #528 owns that
design and its JavaScript-disabled browser proof.

Keep GET and QUERY on the same server-side render surface: the same handler
logic or shared application function should feed the same template and named
results block. Do not create a JSON/REST side channel for the enhanced path.

The executable
[complex QUERY search](../examples/standalone/query_search/README.md) shows the
complete pattern: a JavaScript-disabled GET submits only a compact bookmarkable
subset, while `htmx.ajax("QUERY", ...)` sends the larger faceted input and swaps
the named results block. It uses no response JSON, duplicate partial, or
JavaScript build pipeline.

## Redirects, equivalent resources, and validators

Existing response primitives carry the protocol:

- `307` and `308` preserve QUERY and its body unambiguously.
- `301` and `302` preserve QUERY under RFC 10008, but custom-method client
  behavior varies; test the actual client.
- `303` hands the client to a GET resource.
- `Location` can identify an application-owned GET resource representing the
  query; `Content-Location` can identify the enclosed result representation.
- `ETag` and `Last-Modified` participate in the same conditional evaluation as
  GET and can produce a bodyless `304`.

Equivalent-resource identifiers must be opaque. Never embed raw query content,
credentials, personal data, or other sensitive body values in a URI.

## Caching is explicit and default-off

Configuration-managed caching remains GET-only. To cache eligible QUERY
responses, manually register `CacheMiddleware` with the provisional body-aware
key function:

```python
from chirp.cache.backends.memory import MemoryCacheBackend
from chirp.cache.key import query_cache_key
from chirp.cache.middleware import CacheMiddleware

app.add_middleware(
    CacheMiddleware(
        MemoryCacheBackend(),
        ttl=60,
        query_key_func=query_cache_key,
    )
)
```

The key hashes exact body bytes, request media metadata, target URI, `Accept`,
configured vary headers, and htmx render shape without exposing the raw body.
Cookie, Authorization, `Set-Cookie`, streaming, SSE, non-200, and private
requests bypass QUERY caching. Cached hits preserve render metadata and
re-evaluate ETag/Last-Modified conditions. Use a shared backend, short TTL,
explicit invalidation, and application-specific vary headers for production
experiments.

## Deployment checklist

- Add `QUERY` to `CORSConfig.allow_methods` and allow the request
  `Content-Type` header for cross-origin browser calls.
- Verify every proxy and CDN preserves the method and body. Never rewrite
  QUERY to POST as a compatibility workaround.
- Align Pounce and Chirp request-size limits; the lower ceiling wins.
- Keep raw query bodies out of logs, metrics, traces, and error capture unless
  an explicit redaction policy exists.
- Treat retry and 0-RTT as replay-capable and keep handlers safe/idempotent.
- Test redirect behavior in the actual client.
- Retain a direct-origin path, GET fallback, or equivalent GET resource.

The [interoperability report](http-query-interoperability.md) records exact
Pounce HTTP/1.1, HTTP/2, HTTP/3, Uvicorn, Nginx, Chromium, CORS, redirect,
retry, body-limit, logging, metric, and trace evidence. It certifies no CDN.

## Release gate decision

The experimental release gate is met; the stable promotion gate is not.

| Gate | Status | Evidence or blocker |
| --- | --- | --- |
| Request media, failure, and body-limit semantics | Met | #525 and `tests/test_query_protocol.py` |
| Discovery, redirects, equivalent resources, and validators | Met | #526 and `tests/test_query_response_semantics.py` |
| Typed full-page, fragment, OOB, Stream, Suspense, validation, and DevTools paths | Met | #529 and `tests/contracts/test_query_render_surfaces.py` |
| Collision-safe key plus explicit response-cache opt-in | Met | #530/#531 cache unit and end-to-end tests |
| Browser, ASGI, Pounce, proxy, retry, limit, and observability matrix | Met | #532 and the interoperability report |
| Filesystem/test-client ergonomics | Open | #527 requires a separate public-API decision |
| Declarative htmx transport with native GET fallback | Open | #528 requires an approved client contract |
| Complete static wiring diagnostics and freeze/speculation proof | Open | #533 |
| Canonical complex-search example and no-JavaScript browser proof | Met | #534 and `examples/standalone/query_search` |
| Canonical docs, compatibility statement, and release decision | Met | #535 and this guide |

Therefore release notes and public docs may say **experimental early-adopter
HTTP QUERY support**. They must not say native form support, universal proxy/CDN
support, production-ready QUERY, or stable/first-class QUERY until every open
gate above is complete and reviewed.

## Release verification

The final promotion decision reruns, at minimum:

```bash
uv run ruff check .
uv run ruff format . --check
uv run ty check src/chirp/
uv run pytest tests/test_query_protocol.py tests/test_query_response_semantics.py
uv run pytest tests/contracts/test_query_render_surfaces.py
uv run pytest tests/contracts/test_query_cache_optin_e2e.py
uv run pytest tests/interop/test_query_wire.py
uv run pytest
```

Browser proof additionally runs the QUERY CORS and DevTools Playwright tests.
The full pytest run enforces the repository's configured coverage floor.
The release record must name exact dependency/server versions and preserve the
interoperability caveats rather than inferring universal support from CI.

## Migration notes

- A pre-contract route using bare `methods=["QUERY"]` must add a non-empty
  `query_media_types=(...)` declaration or startup fails.
- Continue using `TestClient.request("QUERY", ...)`; no QUERY shortcut exists.
- Continue using explicit decorator routes; filesystem `query()` is not
  discovered.
- `AppConfig(cache_middleware_enabled=True)` remains GET-only. QUERY cache
  opt-in requires manual `CacheMiddleware(query_key_func=...)` registration.
- Do not document speculative htmx attributes. The only verified enhanced
  browser calls today are programmatic Fetch and `htmx.ajax()`.
