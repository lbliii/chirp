# RFC 009: HTTP QUERY Contract And Compatibility Tier

**Status:** Accepted — #525 request contract implemented; remaining delivery gates pending
**Issue:** [#524](https://github.com/lbliii/chirp/issues/524)
**Saga:** [#519](https://github.com/lbliii/chirp/issues/519)
**Standard:** [RFC 10008](https://www.rfc-editor.org/rfc/rfc10008.html)
**Created:** 2026-07-06

This RFC defines Chirp's intended first implementation of the HTTP `QUERY`
method. Merging this document accepts the design, not every implementation
change. The public route keyword, protocol enforcement, contract rules, cache
behavior, filesystem convention, client integration, and sync-path work remain
separate review units with the proof named below.

Issue #525 implements the public route declaration, freeze-time media-range
validation, request `Content-Type` enforcement, configured body-limit parity,
post-negotiation `Accept` enforcement, protocol error headers, and ASGI-only
sync fallback. Discovery/`OPTIONS`, redirects and validators, client and page
ergonomics, render-surface proof, caching, deployment, and promotion remain
owned by #526-#535.

## 1. Context

RFC 10008 defines `QUERY` as a safe, idempotent, body-bearing request. The
request content and its media type describe a query performed within the scope
of the target resource. It fills the gap between a bookmarkable `GET` and a
body-bearing `POST` whose semantics are not inherently safe.

Chirp already preserves arbitrary method tokens through route compilation and
ASGI request construction:

- `App.route(..., methods=[...])` records caller-supplied methods;
- `AppCompiler` uppercases those methods without restricting their vocabulary;
- `Router` dispatches by the exact method token and includes registered methods
  in `405 Allow`;
- `Request.body()`, `.json()`, `.text()`, and `.form()` read bodies independently
  of the method; and
- the existing return types negotiate HTML independently of the request method.

That is useful substrate, but it is not first-class RFC 10008 support. Chirp
does not currently require a `Content-Type` for `QUERY`, declare query formats,
emit `Accept-Query`, synthesize `OPTIONS`, evaluate conditional dynamic
responses, or key caches by request content. Filesystem pages do not discover a
`query()` handler. `CacheMiddleware` is GET-only, which is the safe current
default.

## 2. Decision summary

Chirp will initially support `QUERY` as an **experimental, explicit-route-only,
ASGI-path feature**.

1. Route authors opt in with `methods=["QUERY"]` and declare supported query
   media ranges with `query_media_types=(...)`.
2. A first-class QUERY route without at least one declared media range is a
   startup error. A declaration on a non-QUERY route is also an error.
3. Chirp enforces request media-type rules before invoking the handler. Existing
   body accessors enforce configured limits exactly as they do for other
   body-bearing methods. Chirp does not sniff content.
4. Handlers keep returning `Page`, `Fragment`, `OOB`, `Suspense`, `Stream`,
   `ValidationError`, `Response`, or `Redirect`. There is no `QueryResult`.
5. Existing `Response` headers and `Redirect` represent equivalent resources,
   indirect results, and redirects. No new response helper is required.
6. `QUERY` bypasses Chirp response caching until a body-and-metadata-aware key
   implementation is accepted and explicitly enabled.
7. Filesystem `query()` discovery, declarative htmx transport, and a
   `TestClient.query()` convenience method are deferred to their own public API
   reviews. The generic `TestClient.request()` is sufficient for protocol-core
   proof.
8. The fused sync path does not handle `QUERY` initially; it falls through to
   ASGI. This avoids a second, weaker protocol implementation.

No `AppConfig` field, feature flag, mandatory dependency, template system,
serialization layer, or new return type is added.

## 3. Compatibility tier and promotion gate

### 3.1 Initial tier

The initial compatibility statement is:

> HTTP QUERY support is experimental. It applies only to routes explicitly
> registered with `methods=["QUERY"]` and declared query media ranges. Server
> transport is supported through Chirp's ASGI path. Client, intermediary,
> cache, filesystem-page, and sync-fast-path support are not implied.

This statement belongs in the request/routing documentation and release notes
when behavior ships. This RFC alone is not a public claim that QUERY works.

### 3.2 Promotion to first-class support

Promotion requires all of the following:

- request media-type, malformed-content, response negotiation, body-limit, and
  error-status tests;
- discovery, redirect, equivalent-resource, conditional-request, and
  multi-value-header tests;
- `Page`, `Fragment`, OOB, Suspense, and `Stream` proof for htmx and non-htmx
  requests, including missing-block failures;
- a collision-safe cache key and an explicit QUERY cache opt-in;
- same-origin and cross-origin browser proof, including CORS preflight;
- Pounce plus supported ASGI transport proof for available HTTP versions;
- `app.check()`, freeze, speculation, route explorer, autodoc, and surface-diff
  coverage;
- a no-JavaScript GET fallback and an executable complex-search example;
- documentation, release notes, and a release-gate decision.

Until that convergence, documentation must say “experimental explicit-route
support,” not “native form support,” “htmx support,” “cacheable by Chirp,” or
“production-ready QUERY.”

## 4. Route declaration

### 4.1 Public setup surface

The proposed route signature adds one keyword-only argument:

```python
def route(
    path: str,
    *,
    methods: list[str] | None = None,
    name: str | None = None,
    referenced: bool = False,
    template: str | None = None,
    inline: bool = False,
    query_media_types: tuple[str, ...] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]: ...
```

Example:

```python
@app.route(
    "/search",
    methods=["QUERY"],
    query_media_types=("application/x-www-form-urlencoded",),
)
async def search(request):
    form = await request.form()
    return Page("search.html", q=form.get("q", ""))
```

`query_media_types` is route metadata, not an `Accept` replacement and not a
parser registry. It declares the request content formats the target resource
understands for QUERY. Values are media ranges using the RFC 10008
`Accept-Query` model, including optional media-type parameters and only the
wildcards permitted by the RFC (`*/*` and `type/*`).

At freeze, Chirp validates and normalizes the declaration into an immutable,
deterministically ordered tuple on the compiled route. Invalid syntax,
duplicates after normalization, a missing declaration on a QUERY route, or a
declaration on a route without QUERY raises an actionable `ConfigurationError`
that names the route and value.

This keyword is a public API change. Its implementation therefore needs the
separate public-API check-in required by the repository constitution, plus
`docs/public-api.md`, tests, and changelog/migration collateral. No new top-level
export is needed.

### 4.2 Filesystem pages

The first release does **not** add `query()` to route-directory discovery.
Current discovery recognizes `get`, `post`, `put`, `delete`, `patch`, `head`,
and `options`, but there is no established place for per-handler query media
ranges.

Issue #527 may propose a page convention only after it defines where the
declaration lives, how multiple handlers in one module remain unambiguous, and
how `app.check()` reports mistakes. Adding `query()` without that declaration
would create a route Chirp cannot validate.

### 4.3 Internal representation

`PendingRoute` and frozen `Route` receive a nullable, immutable tuple of query
media types. `mount_app()` preserves it. The route compiler owns validation and
normalization before router publication. The internal `HypermediaProgram` may
record the normalized tuple for inspection, but it remains private until the
structured inspection API is separately designed.

The media-range parser and `Accept-Query` serializer live under
`src/chirp/http/`. They are private in the first increment. The serializer must
produce an RFC 9651 Structured Field List, including correct token-versus-string
encoding and parameter mapping; joining raw declaration strings with commas is
not sufficient.

## 5. Request processing and failure semantics

The server performs QUERY protocol validation after route matching and before
handler invocation. Middleware still sees the request through the normal
pipeline; no alternate dispatch stack is created.

For a declared QUERY route:

1. missing `Content-Type` returns `400 Bad Request`;
2. a syntactically invalid `Content-Type` returns `400 Bad Request`;
3. a well-formed but undeclared media type returns `415 Unsupported Media
   Type` with `Accept-Query`;
4. `Request.body()`, `Request.stream()`, and `Request.form()` apply the existing
   general and upload-specific limits, producing `413 Payload Too Large` at the
   same byte boundaries as POST or PUT;
5. Chirp never infers or replaces the declared content type from the bytes;
6. format-specific syntax failures return `400`; and
7. syntactically valid queries that cannot be processed semantically return
   `422 Unprocessable Content`.

Steps 6 and 7 remain parser/application responsibilities because arbitrary
media types have arbitrary syntax and semantics. Handlers use the stable
`HTTPError`/`Response` surface, or `ValidationError` where its fragment
semantics fit. Built-in `request.json()` and `request.form()` behavior may gain
QUERY-specific error mapping only through a separate request-API review; the
protocol layer must not catch unrelated `ValueError` exceptions from user
code and relabel them as malformed content.

After the existing return-type negotiator selects a response content type, the
QUERY protocol layer compares it with request `Accept`. An unsatisfied value
returns `406 Not Acceptable`; it does not create a second return-type branch.

Error detail must name the route and the missing, malformed, unsupported, or
expected media type. Error handlers continue to receive ordinary `HTTPError`
instances. Framework-generated `400`, `405`, `406`, `413`, and `415` responses
preserve protocol headers even when a custom error page is used; this may
require tightening the existing custom-error header preservation path.

## 6. Rendering and return types

`QUERY` is request semantics, not a render surface.

- A non-htmx request returning `Page` receives the normal full document.
- An htmx request returning `Page` receives the same negotiated narrow render
  path used by other methods.
- `Fragment`, OOB, Suspense, and `Stream` keep their existing template/block
  rules and failure behavior.
- Missing required blocks still raise `BlockNotFoundError`; no empty swap is
  substituted.
- `EventStream` remains the post-load SSE type. QUERY does not turn it into a
  query response or create a second streaming primitive.

The implementation must not edit `templating/render_plan.py`,
`templating/returns.py`, or `templating/suspense.py` merely to recognize the
method. If proof exposes a real render-pipeline gap, that change gets its own
design check-in.

## 7. Discovery and `Accept-Query`

### 7.1 `405 Allow`

The router already includes exact registered methods in `405 Allow`. A path
with a declared QUERY route therefore includes `QUERY`. Existing GET/HEAD
semantics do not change as a side effect of this work.

When the path has a QUERY declaration, Chirp also adds the serialized
`Accept-Query` value to its generated `405` response. A custom error handler
must not silently drop either `Allow` or `Accept-Query`.

### 7.2 `OPTIONS`

An explicit user `OPTIONS` route always wins. Otherwise, when a path has a
declared QUERY route and Chirp owns method dispatch, it generates a bodyless
`204` response with:

- `Allow`: the methods registered for that path plus `OPTIONS`; and
- `Accept-Query`: the declared formats when QUERY is registered.

This is path-specific discovery, not a server-wide capability claim. CORS
middleware may answer a preflight `OPTIONS` request earlier; it must include
`QUERY` only when the operator explicitly allows it.

Automatic OPTIONS is a protocol-shape change and requires a dedicated review
with existing explicit-OPTIONS and 405 behavior tests.

### 7.3 Other responses

Chirp adds `Accept-Query` to framework-generated QUERY protocol errors and
discovery responses. Successful application responses may include it through
`Response.with_header()`. Automatically decorating every successful or
streaming response is deferred unless interoperability proof shows it is
needed; RFC 10008 makes the field optional.

The field applies to the path independent of its URI query component. Its
order is insignificant. Token and String items with identical media values are
processed identically.

## 8. Equivalent resources, redirects, and validators

### 8.1 `Location` and `Content-Location`

Chirp does not create or persist equivalent resources. Application code owns
their identity, authorization, lifetime, and storage.

- `Location` on a successful QUERY response identifies a GET resource that
  represents the QUERY request and can repeat it without resending the content.
- `Content-Location` identifies a GET resource corresponding to the enclosed
  result representation.
- The two fields may be different and are not generated from request content.
- Temporary identifiers containing sensitive raw query content are forbidden.

Existing `Response.with_header()` is sufficient. No public equivalent-resource
helper is added.

### 8.2 Redirects

Existing `Redirect(url, status=...)` remains the HTTP primitive:

| Status | QUERY behavior |
| --- | --- |
| `301`, `302`, `307`, `308` | Client repeats QUERY at `Location`; the POST-to-GET exception for `301`/`302` does not apply. |
| `303` | Client performs GET at `Location`. |

Chirp must not rewrite one status to another. Transport tests, not unit tests of
the dataclass alone, prove method behavior. `HX-Redirect` is a browser
navigation instruction and normally initiates GET; it is not evidence that an
HTTP QUERY redirect preserved the method. `FormAction` and `MutationResult`
remain mutation-oriented and are not QUERY redirect helpers.

### 8.3 Conditional requests

The selected representation for QUERY is the selected representation of its
equivalent GET resource. Application code supplies consistent `ETag` and/or
`Last-Modified` validators on both surfaces.

Issue #526 will add protocol proof for `If-None-Match`, `If-Modified-Since`,
`If-Match`, and `If-Unmodified-Since`. Any generic dynamic-response evaluator
must be shared by QUERY and GET rather than copied from the file sender, must
preserve htmx/full-page variance, and must not buffer `Stream` merely to invent
a validator. Responses without a validator process normally.

### 8.4 Range

Range semantics are the same as GET for a representation that supports ranges.
Chirp's current generic HTML responses do not promise byte-range support, and
this RFC does not add it. `FileResponse` keeps its existing behavior. Query
formats should prefer their own paging/limiting semantics. This is an explicit
initial deferral, not a claim that QUERY changes Range semantics.

## 9. Async and sync execution

The first implementation is ASGI-only. `handle_sync()` returns `None` for
`QUERY` before route invocation so Pounce falls through to the ASGI path. This
is required even for a sync handler because `SyncRequest` has no body API and
cannot enforce the declared media type and body limits.

Before that change lands, the implementation PR must record:

- the current QUERY behavior of the fused path;
- a focused measurement showing no material GET fast-path regression from the
  early method guard; and
- ASGI parity tests for sync and async QUERY handlers.

Fused QUERY support is a later optimization. It requires body access,
media-type enforcement, error/header parity, and its own measurement plan; it
must not become an independent protocol implementation.

### #525 sync-guard receipt

On 2026-07-06, a focused in-process synthetic measurement on arm64 macOS with
CPython 3.14.2t compared the frozen GET fused path before and after the early
`method == "QUERY"` guard. Across nine repeats of 200,000 calls, the median was
1125.6 ns/call before and 1134.6 ns/call after (+0.8%); the best samples were
1069.1 and 1065.6 ns/call respectively. This is within run-to-run noise and is
not evidence about production throughput; it records that the required QUERY
escape did not produce a material GET fast-path regression in this focused
workload.

## 10. Caching

Although RFC 10008 permits QUERY responses to be cached, the cache key must
include request content and related metadata. Chirp's current key includes
method, path, URI query, and htmx shape, but not the body or content metadata.

Therefore:

- `CacheMiddleware` continues to bypass every non-GET request;
- built-in key functions are not advertised as safe for QUERY;
- no QUERY response is stored until #530 lands a deterministic key including
  exact body bytes, content type and parameters, content encoding, target
  path/query, response `Accept`, configured vary inputs, htmx/full-page shape,
  target, authorization/cookie bypass, and other selected-representation
  metadata; and
- #531 may add explicit opt-in caching only after collision, body-reuse,
  privacy, streaming bypass, validator, backend-failure, and contention proof.

Semantic normalization is off by default. A future normalization hook must be
media-type-specific, affect only the key, honor `no-transform` as required by
the accepted policy, and prove it cannot collapse semantically distinct
queries. Raw sensitive content must never appear in cache key strings or logs.

## 11. Browser and progressive-enhancement boundary

Native HTML forms cannot submit QUERY. The first server increment therefore
does not claim a no-JavaScript client path.

The canonical product shape is a GET fallback plus an enhanced QUERY request:

- the ordinary form submits a short/bookmarkable GET representation;
- enhancement serializes the same successful-controls model into the declared
  query content type and sends QUERY; and
- both paths return from the same template and named blocks.

Issue #528 owns the declarative htmx design and must prove the actual htmx
version and browser transport before docs claim an attribute syntax. No
JavaScript build pipeline is introduced. Cross-origin Fetch requests require a
CORS preflight because QUERY is not CORS-safelisted.

## 12. Security and observability

QUERY is safe and idempotent by protocol. Chirp cannot prove that arbitrary
handler code has no side effects, so the boundary is layered:

- docs state that QUERY handlers must not perform requested mutations;
- `app.check()` flags mutation-oriented route/action declarations where they
  are statically knowable;
- CSRF and audit mutation sets continue to classify only actual mutation
  methods; QUERY is not added merely because it has a body;
- authentication, authorization, rate limits, body limits, and ordinary
  middleware still apply;
- Chirp and DevTools do not log raw query content by default;
- temporary equivalent-resource URLs must not contain sensitive query content;
  and
- CORS configuration must name QUERY explicitly for cross-origin use.

“Not in the URI” does not mean secret. Operators still review access logs,
reverse proxies, tracing, body capture, retries, and temporary-resource policy.

DevTools may show method, declared/received media type, byte count, target,
selected block, render intent, timing, validator/cache decision, and errors. It
must redact or omit the raw body unless an existing explicit debug policy says
otherwise.

## 13. Contracts, inspection, freeze, and speculation

Issue #533 owns startup checks. Detectable failures include:

- a defensive snapshot inconsistency between a QUERY route and its compiled
  media ranges (normal registration rejects this earlier);
- approved client syntax targeting a route without QUERY or with a mismatched
  content type;
- statically knowable mutation-oriented actions on QUERY;
- CORS declarations that claim cross-origin QUERY without allowing the method
  and content header; and
- route/template/target mismatches already covered for other methods.

Messages name the template, route, method, media type, or target. Existing
GET/POST severities do not change. Any new severity or default still requires a
separate check-in.

Freeze and speculative navigation remain GET-only. QUERY routes are never
executed during freeze, prefetch, prerender, route smoke, or contract discovery
unless a test or tool supplies an explicit body and media type. Route explorer,
autodoc, and structured inspection may display declared formats without
executing the route.

## 14. RFC 10008 traceability matrix

The matrix maps every normative or interoperability-significant section of RFC
10008 to planned Chirp proof. “Deferred” means the first experimental release
does not claim that optional capability.

At drafting time, RFC 10008 has two **reported**, not yet verified, technical
errata. Erratum 9013 removes a response-only `Vary` field accidentally shown in
a request example. Erratum 9016 corrects malformed example HTTP dates. Neither
changes the method contract below; tests use valid request fields and
IMF-fixdate values.

| RFC section | Requirement or behavior | Chirp decision | Proof / owner |
| --- | --- | --- | --- |
| §2 | QUERY initiates a safe, idempotent query scoped by the target resource. | Explicit QUERY route; handler side effects remain app responsibility; contracts catch statically knowable mutation shapes. | #525 protocol tests; #533 contract tests |
| §2 | Missing or content-inconsistent `Content-Type` must fail. | Missing/invalid header is framework `400`; no sniffing; format parser maps inconsistent bytes to `400`. | #525 `TestClient` matrix |
| §2 | Target URI query remains part of resource identity. | Router and request path/query behavior is unchanged; cache key includes both path and URI query. | #525 routing tests; #530 key tests |
| §2 | `200` encloses a processed result; other 2xx retain HTTP meaning. | Existing `Response` and typed returns; no QUERY-specific result type. | #529 negotiation tests |
| §2.1 | Unsupported request media type may be `415` with `Accept-Query`. | Declared range mismatch returns `415` plus structured `Accept-Query`. | #525 HTTP/server tests |
| §2.1 | Semantically unprocessable content may be `422`. | Handler uses `HTTPError`, `Response`, or compatible `ValidationError`; htmx errors retain fragment safety. | #525 and #529 end-to-end tests |
| §2.1 | Unsatisfied response `Accept` may be `406`. | Validate `Accept` against the content type selected by existing return negotiation. | #525 accept tests |
| §2.2 | Equivalent resource incorporates target, content, and metadata. | App-owned GET resource; framework does not invent identity or persistence. | #526 example matrix |
| §2.3 | `Content-Location` may identify the query result resource. | Existing response header API; app owns lifetime/auth. | #526 direct-result tests |
| §2.4 | `Location` on 2xx may identify the equivalent resource. | Existing response header API; app owns lifetime/auth. | #526 direct-result tests |
| §2.5 | `301`/`302`/`307`/`308` repeat QUERY; `303` hands off to GET. | Preserve status/Location; no POST rewrite; distinguish `HX-Redirect`. | #526 client and Pounce transport tests |
| §2.6 | Conditional fields apply to the selected equivalent representation. | Shared GET/QUERY validators; no validator invented for streams. | #526 ETag/date/precondition tests |
| §2.7 | QUERY responses may be cached. | Deferred and bypassed by default. | #531 opt-in cache tests |
| §2.7 | Cache key must include content and related metadata. | Required before opt-in; exact bytes by default. | #530 collision/property/body-reuse tests |
| §2.7 | Semantic normalization may affect only the key. | Deferred; media-type-specific proof required; raw request unchanged. | Explicit future RFC/check-in |
| §2.8 | Range has GET semantics; query-native paging is preferred. | Existing range-capable responses only; no generic dynamic range claim. | #526 documentation/protocol test |
| §3 | `Accept-Query` is an RFC 9651 Structured Field List of media ranges. | Private validated serializer; no raw comma join. | #526 serializer/header tests |
| §3 | Token/String item forms are semantically identical; parameters map to Structured Field parameters. | Normalize to one internal media-range model; compare by semantics. | #526 parser/round-trip tests |
| §3 | Only `*/*` and `type/*` wildcard forms are supported; order is insignificant. | Freeze validation; deterministic order. | #525 registration tests |
| §3 | Field value applies by path, ignoring URI query. | Route metadata is path/method scoped, not request-query scoped. | #526 discovery tests |
| §4 | Temporary resource URIs should omit sensitive request content. | App-owned opaque identifiers; contract/docs warning; no generated URI. | #526 security tests/review |
| §4 | Incorrect normalization can return the wrong response. | No normalization initially; collision proof before opt-in. | #530 property tests |
| §4 | Cross-origin QUERY requires preflight. | Existing CORS middleware, explicit `QUERY` allow-list entry, browser proof. | #532 browser/intermediary tests |

Normative HTTP semantics inherited from RFC 9110 and caching rules inherited
from RFC 9111 remain applicable. Their implementation proof belongs to the
same issue named in the matrix rather than a second QUERY-only abstraction.

## 15. Cross-surface contract checklist

| Surface | Decision and required collateral |
| --- | --- |
| Public API | Add only `App.route(..., query_media_types=...)`; update `docs/public-api.md`, signature tests, and migration note when implemented. |
| Protocol | ASGI validation, 400/405/406/413/415/422 behavior, OPTIONS, `Allow`, `Accept-Query`, redirects, validators. |
| Request/response | Reuse `Request` body methods, `HTTPError`, `Response`, and `Redirect`; preserve multi-value headers. |
| Routing | Exact QUERY token; route-scoped immutable media metadata; explicit OPTIONS wins. |
| Templates/rendering | Existing typed returns and named blocks only; no render-pipeline change planned. |
| UI/client | No native form claim; GET fallback plus separately reviewed enhancement. |
| Contracts | New QUERY-specific checks without changing existing severity defaults. |
| Cache | Hard default bypass until compliant key and explicit opt-in. |
| Security | Safe-method classification, authorization, body limits, CORS, redaction, opaque temporary URLs. |
| Testing | `TestClient.request()` protocol core, browser/Pounce transport, htmx/full page, malformed inputs, sync/async handlers. |
| Pages | No `query()` convention in initial release; separate design in #527. |
| Freeze/speculation | Never execute body-dependent QUERY routes implicitly. |
| Docs/examples | Request/routing docs and canonical complex-search example only after executable behavior exists. |
| Changelog | No fragment for this design-only RFC; each user-visible implementation PR carries its own fragment. |
| Site/generated output | No generated-site edit for this RFC. Publish source-backed user docs only with implementation. |
| Benchmarks | Measure GET sync-guard impact and QUERY body-buffer/key cost in the relevant implementation PRs. |

### 15.1 Implementation and proof map

| Work | Primary implementation targets | Required proof and collateral |
| --- | --- | --- |
| #525 request contract | `src/chirp/app/`, `src/chirp/routing/route.py`, `src/chirp/http/`, `src/chirp/server/handler.py` | route/request/server tests; `TestClient` 400/406/413/415/422 matrix; public API, request docs, migration note, changelog |
| #526 response semantics | `src/chirp/routing/router.py`, `src/chirp/server/`, `src/chirp/http/response.py` | 405/OPTIONS/header tests; redirect transport matrix; conditional response tests; protocol docs and changelog |
| #527/#528 ergonomics | `src/chirp/testing/`, `src/chirp/pages/`, approved client integration | helper and discovery tests; browser test with GET fallback; testing/pages/client docs and changelog |
| #529 render proof | existing negotiation, DevTools, and contract surfaces; render pipeline only after a separate check-in | `tests/contracts/` through `TestClient`; htmx/non-htmx, missing-block, stream, sync/async, and browser DevTools proof |
| #530/#531 cache | `src/chirp/cache/key.py`, `src/chirp/cache/middleware.py`, backends | collision/property/body-reuse/private-request/stream/concurrency tests; cost measurement; cache docs and changelog |
| #532 deployment | CORS middleware and external Pounce/ASGI/intermediary harnesses | browser preflight, available HTTP versions, retry and proxy behavior; deployment fallback docs |
| #533 contracts | `src/chirp/contracts/`, route explorer, autodoc, surface diff, freeze/speculation | `tests/contracts/`, freeze/speculation non-execution tests, existing-severity regression tests; contract docs and changelog |
| #534/#535 adoption | executable complex-search example and canonical docs/site sources | example smoke/browser tests, docs link checks, release gate and compatibility statement |

## 16. Delivery order and implementation gates

1. **#524 — this RFC:** design only.
2. **#525:** public route metadata check-in, request validation, failure
   semantics, body limits, and protocol tests.
3. **#526:** discovery, redirects, equivalent-resource headers, and conditional
   behavior.
4. **#527/#528:** testing ergonomics, filesystem/client proposals, and GET
   fallback.
5. **#529:** typed-return, streaming, and DevTools proof; render changes require
   their own check-in.
6. **#530:** cache-key design and measurements; cache-key changes require their
   own check-in.
7. **#531/#532:** opt-in cache and deployment/intermediary proof.
8. **#533–#535:** contracts, example, docs, and release gate.

The first public release can occur after #525 and #526 only under the narrow
experimental statement in §3. Promotion waits for the complete gate.

## 17. Rejected alternatives

- **New `QueryResult` return type:** rejected because method semantics do not
  create a new render intent.
- **`AppConfig.query_enabled`:** rejected because explicit route registration
  is the opt-in and speculative config would widen public API.
- **Automatic filesystem `query()` immediately:** rejected because no declared
  media-format convention exists yet.
- **Treating QUERY as POST internally:** rejected because it would corrupt
  safety, retry, redirect, CSRF, audit, and cache semantics.
- **Treating QUERY as GET with a body:** rejected because GET content has no
  generally defined request semantics and QUERY has its own discovery rules.
- **Accept every content type and let handlers guess:** rejected because it
  prevents reliable `415` and `Accept-Query` behavior.
- **Enable current cache keys for QUERY:** rejected because different request
  bodies would collide.
- **Run QUERY through the fused sync path immediately:** rejected because
  `SyncRequest` cannot currently enforce the body contract.
- **Invent equivalent-resource URLs from a body hash:** rejected because URL
  lifetime, authorization, disclosure, and persistence are application policy.

## 18. References

- [RFC 10008 — The HTTP QUERY Method](https://www.rfc-editor.org/rfc/rfc10008.html)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html)
- [RFC 9651 — Structured Field Values for HTTP](https://www.rfc-editor.org/rfc/rfc9651.html)
- [Fetch Standard — methods and CORS](https://fetch.spec.whatwg.org/#methods)
- [Reported RFC 10008 errata](https://errata.rfc-editor.org/search/?rfc_number=10008)
