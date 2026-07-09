---
title: Experimental HTTP QUERY
description: Adopt safe body-bearing searches with explicit routes, GET fallbacks, and verified deployment boundaries.
draft: false
weight: 25
lang: en
type: doc
tags: [routing, http-query, hypermedia, experimental]
keywords: [QUERY, RFC 10008, search, GET fallback, CORS, cache]
category: guide
---

HTTP `QUERY` is a safe, idempotent, body-bearing method for read-only queries
whose structured input would make an impractical URI. Chirp offers
**experimental early-adopter support** on explicit ASGI routes. Stable
promotion is not approved yet.

Use GET for ordinary, bookmarkable searches and every native HTML form. Choose
QUERY only when the input is genuinely too large or structured for a useful
URI, keep the handler free of requested mutations, and retain a GET fallback
or equivalent GET resource.

## Declare the route

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

`query_media_types` is mandatory on QUERY routes and invalid elsewhere. Chirp
validates the media ranges at freeze time. Support is explicit-route-only:
there is no filesystem `query()` convention, `TestClient.query()` helper,
`AppConfig` switch, or QUERY-specific return type.

Tests use the generic request API:

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

## Failure and discovery contract

| Input or request | Result |
| --- | --- |
| Missing/malformed `Content-Type` | `400` |
| Undeclared request media type | `415` plus `Accept-Query` |
| Body over the effective limit | `413` |
| Response cannot satisfy `Accept` | `406` |
| Method mismatch | `405` with `Allow` and `Accept-Query` |
| Generated discovery | bodyless `204 OPTIONS` with both headers |

An explicit `OPTIONS` route wins. Parsers/handlers distinguish malformed query
content (`400`) from valid syntax that cannot be processed (`422`).

QUERY uses Chirp's normal return-type architecture and one-template/named-block
contract. A direct request can receive the full `Page`; an htmx request can
receive the named results block from the same template. OOB, `Stream`,
`Suspense`, validation, redirects, and fail-loud missing-block behavior do not
gain a QUERY-specific side channel.

## GET fallback and client boundary

Native forms cannot submit QUERY. Use `<form method="get">` for the
unenhanced path. Programmatic Fetch and `htmx.ajax("QUERY", ...)` are covered
by browser tests, but Chirp does not publish a declarative `hx-query` syntax or
stable adapter. Do not invent one in application docs.

The canonical
[complex QUERY search](https://github.com/lbliii/chirp/tree/main/examples/standalone/query_search)
is executable proof: its JavaScript-disabled form submits only a compact,
bookmarkable GET subset, while htmx sends the larger faceted input in a QUERY
body and swaps the same template's named results block. There is no JSON
response path, duplicate partial, or JavaScript build pipeline.

Cross-origin Fetch triggers a CORS preflight. Add QUERY to
`CORSConfig.allow_methods` and allow the declared `Content-Type` header.

## Redirects, validators, and result identity

- Prefer `307`/`308` when the client must repeat QUERY and its body.
- Use `303` to hand off to a GET resource.
- Test `301`/`302` custom-method behavior in the actual client.
- Use application-owned opaque `Location`/`Content-Location` values; never
  encode sensitive query content into a URI.
- Application `ETag` and `Last-Modified` values participate in conditional
  evaluation and can produce `304`.

## Cache only by explicit opt-in

Configuration-managed caching remains GET-only. A controlled experiment can
manually supply Chirp's provisional body-aware key:

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

Private/authenticated requests, `Set-Cookie`, streaming/SSE, non-200 responses,
and key/backend failures bypass. Use short TTLs, application-specific vary
headers, explicit invalidation, and a shared backend when evaluating this in a
multi-worker deployment.

## Deployment boundary

- Verify every proxy/CDN preserves the method and body. Never rewrite QUERY to
  POST.
- Align Pounce and Chirp body limits; the lower limit wins.
- Keep body bytes out of logs, metrics, traces, and error capture unless a
  redaction policy explicitly permits them.
- Treat retry and HTTP/3 0-RTT as possible replay.
- Keep a direct-origin or GET fallback.

Chirp's matrix covers Pounce HTTP/1.1, HTTP/2, and HTTP/3, Uvicorn, Nginx,
Chromium Fetch/CORS, redirects, retry, body limits, access logs, metrics, and
traces. It certifies no CDN. See
[[docs/quality/deployment/query-interoperability|HTTP QUERY Interoperability]]
for operator details.

## Compatibility and release gate

| Capability | Status |
| --- | --- |
| Request/response protocol, typed rendering, cache opt-in, and tested transport matrix | Implemented |
| Filesystem/test-client ergonomics (#527) | Open |
| Declarative htmx plus no-JavaScript GET proof (#528) | Open |
| Complete static diagnostics (#533) | Open |
| Canonical complex-search example (#534) | Implemented and browser-tested |
| Stable/first-class promotion | Not approved |

The allowed claim is **experimental early-adopter HTTP QUERY support**. Do not
claim native form support, universal intermediary compatibility,
production-ready QUERY, or stable QUERY.

For implementation traceability and the final promotion checklist, see the
[canonical adoption guide](https://github.com/lbliii/chirp/blob/main/docs/http-query.md)
and [RFC 009](https://github.com/lbliii/chirp/blob/main/docs/rfcs/009-http-query.md).
