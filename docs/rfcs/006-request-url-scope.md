# RFC 006: Request URL Scope For Tenant And Base-Path Apps

**Status:** Initial API implemented
**Author:** (proposal)
**Created:** 2026-05-09
**Depends on:** RFC 003 (named routes), RFC 004 (`url_for`)

**Decision:** keep `app.url_for(...)` app-root deterministic. Add an
immutable request URL scope on `Request`, plus explicit request-aware helpers:
`request.with_url_scope(...)`, `request.scoped_url(path)`, and
`request.url_for(name, **params)`. Template `url_for` becomes request-aware
only for request renders and only when the app has not registered its own
`url_for` global.

**Implemented:** 2026-05-09. `RequestUrlScope` is provisional public API.

---

## 1. Problem Statement

Large Chirp products sometimes serve one route tree through more than one
public URL shape. ELBYSODIC is the current research case: product routes such
as `/boards/{board_slug}` are also reachable through shared-host tenant URLs
such as `/c/{community_slug}/boards/{board_slug}`.

Today, Chirp's `url_for` intentionally returns app-root paths. That keeps
background renders, SSE generators, and tests deterministic, but it leaves
tenant/base-path apps with no supported way to say "for this request, links and
redirects should stay under this public prefix." Downstream apps can work
around this with request path rewriting and rendered HTML rewriting, but that
is brittle: it touches private request state, misses non-HTML URL surfaces, and
turns htmx/SSE URL behavior into regex policy.

Chirp needs a request-scoped URL story that supports tenant-like prefixes
without changing product ownership. The product still decides which tenant is
valid and which paths are scoped; Chirp provides safe URL composition.

---

## 2. Non-Goals

- **No full multi-tenancy framework.** Chirp will not own communities, tenants,
  roles, permissions, host aliases, billing, or onboarding.
- **No automatic HTML rewriting.** Chirp should not mutate arbitrary rendered
  markup to discover URLs after the fact.
- **No implicit global prefix.** Background tasks, startup checks, static
  rendering, and EventStream generators may not have a current request.
- **No `url_for` breaking change.** `app.url_for(...)` stays app-root relative
  unless a later accepted RFC explicitly changes that contract.
- **No absolute URL support.** Scheme/host generation remains out of scope.

---

## 3. Design Sketch

### 3.1 New Request URL Scope

Introduce an immutable request URL scope published by middleware:

```python
@dataclass(frozen=True, slots=True)
class RequestUrlScope:
    prefix: str

    def apply(self, path: str) -> str: ...
```

The accepted storage API is request-object based. Middleware creates a scoped
request by copying the frozen request:

```python
scoped_request = request.with_url_scope(RequestUrlScope(prefix="/c/acme"))
request.url_scope
```

`RequestUrlScope(prefix=...)` normalizes prefixes to one leading slash and no
trailing slash, except the empty/root scope. It applies only to app-root paths;
absolute URLs, protocol-relative URLs, anchors, and non-root relative paths are
returned unchanged so products can keep external and local policy explicit.

### 3.2 Scoped URL Helpers

Keep `app.url_for(...)` unchanged. Add request-aware composition points:

```python
request.url_for("boards.detail", board_slug="ic")
# -> "/c/acme/boards/ic" when the request has prefix="/c/acme"

request.scoped_url(app.url_for("boards.detail", board_slug="ic"))
# -> same result, useful for redirects and existing helpers
```

`request.url_for(...)` requires the request to have an app reference. If a
synthetic request was not created by Chirp's app/server path, it raises a clear
runtime error naming the missing app binding.

Templates receive a request-aware `url_for` only when rendering inside a
request. This keeps RFC 004 `setdefault` semantics: user-defined template
globals still win. Background renders and app-level renders without a request
continue to use app-root `app.url_for(...)`.

### 3.3 Redirects

Redirects should remain explicit. Chirp can provide helper methods, not hidden
rewrite behavior:

```python
return Redirect(request.scoped_url(app.url_for("boards.detail", board_slug="ic")))
```

An optional convenience can be considered later:

```python
return Redirect.to_route(request, "boards.detail", board_slug="ic")
```

That helper must still render a normal `Redirect` with `Location` and
`HX-Redirect` semantics unchanged.

### 3.4 Fragment And Htmx URLs

Fragment URLs compose from scoped route URLs:

```jinja
hx-get="{{ fragment_url(url_for('boards.detail', board_slug=board.slug), 'thread_list') }}"
```

When template `url_for` is request-aware, the generated fragment route should
carry the public prefix:

```text
/_frag/c/acme/boards/ic?block=thread_list
```

This keeps the current `/_frag{path}?_b={block}` shape. Product middleware that
accepts tenant-prefixed full-page URLs must also strip the accepted request
scope when a fragment request arrives under `/_frag/<scope>/...`. Chirp does
not add a second query-encoded local-path protocol in the first implementation.

### 3.5 SSE Endpoints

SSE endpoint attributes such as `sse-connect` should be generated through the
same request-aware URL helper:

```jinja
<div sse-connect="{{ url_for('threads.stream', thread_id=thread.id) }}">
```

EventStream generators are a special case: they often run after the initial
render and may outlive request context. They should not call ambient
`url_for`. If they need scoped URLs, the handler captures the scoped prefix or
precomputed URLs before returning `EventStream`.

---

## 4. Worked Examples

### 4.1 Full Page

Route:

```python
@app.route("/boards/{board_slug}", name="boards.detail")
def board(...): ...
```

Request path:

```text
/c/acme/boards/ic
```

Middleware validates `acme`, rewrites routing to `/boards/ic`, and attaches
`RequestUrlScope(prefix="/c/acme")`.

Template:

```jinja
<a href="{{ url_for('boards.detail', board_slug='ooc') }}">OOC</a>
```

Rendered output:

```html
<a href="/c/acme/boards/ooc">OOC</a>
```

### 4.2 Boosted Fragment Navigation

```jinja
<a hx-get="{{ url_for('boards.detail', board_slug=board.slug) }}"
   hx-target="#main"
   hx-select="#page-root">
  {{ board.name }}
</a>
```

Expected output under `/c/acme`:

```html
<a hx-get="/c/acme/boards/ic" hx-target="#main" hx-select="#page-root">
```

### 4.3 Login Redirect With `next`

```python
next_url = request.scoped_url(request.path_with_query)
return Redirect(app.url_for("login", next=next_url))
```

If `request.path_with_query` is `/boards/ic?page=2` and the scope prefix is
`/c/acme`, the redirect is:

```text
/login?next=%2Fc%2Facme%2Fboards%2Fic%3Fpage%3D2
```

Login itself stays unscoped unless product middleware scopes it deliberately.

### 4.4 SSE Link

```jinja
<section sse-connect="{{ url_for('threads.stream', thread_id=thread.id) }}">
```

Expected output:

```html
<section sse-connect="/c/acme/threads/42/stream">
```

---

## 5. Compatibility

- Existing `app.url_for(...)` tests should continue to pass unchanged.
- Existing templates that call `url_for` outside a request should keep app-root
  output.
- Apps that already register a custom `url_for` global keep their global.
- Static files, health checks, login, logout, and network/global pages remain
  product policy. Chirp only applies prefixes when the request scope says to.
- `mount_app` prefixes and request URL scopes are different layers:
  `mount_app("/admin", sub)` changes the app route path; request URL scope
  changes the public URL for the active request.

---

## 6. Required Proof For Initial Implementation

- `tests/test_url_for.py` keeps all existing app-root assertions.
- New tests cover:
  - request-scoped `url_for` in a full-page render;
  - boosted htmx link generation;
  - `Redirect` built from `request.scoped_url(...)`;
  - query-string `next` preservation;
  - SSE endpoint attribute generation;
  - no ambient prefix in background/template renders without a request.
  - `fragment_url(request.url_for(...), block)` preserves the current
    `/_frag<public-path>?_b=<block>` protocol.
- Browser smoke for one shell example if the implementation changes htmx
  navigation behavior.
- `app.check()` remains deterministic without a request scope.

---

## 7. Decision Matrix

| Question | Decision | Rationale |
| --- | --- | --- |
| First public API | Provide both `request.scoped_url(path)` and `request.url_for(name, **params)` | The first composes with existing helpers and redirects; the second keeps templates and handlers concise. |
| Fragment URL shape | Keep `/_frag<public-path>?_b=<block>` | It preserves RFC 003/004 composition and avoids a second fragment protocol. |
| Redirect convenience | Defer `Redirect.to_route(...)` | `Redirect(request.url_for(...))` is explicit and does not require changing redirect semantics. |
| Template injection | Inject only during request renders and only under `setdefault` semantics | Background renders stay deterministic; user globals still win. |
| Automatic HTML mutation | Reject for this RFC | URL scope must be generated at URL composition points, not by rewriting rendered documents. |

## 8. Parity Matrix

| Contract | API/CLI | Programmatic | Protocol | Schema/Types | Docs | Examples | Tests |
| --- | --- | --- | --- | --- | --- | --- | --- |
| App-root route reversal | `app.url_for` unchanged | Background renders unchanged | Existing route paths unchanged | No new route schema | RFC 004 remains valid | Existing examples unaffected | Existing `tests/test_url_for.py` assertions stay green |
| Request URL scope | No CLI surface | `RequestUrlScope`, `request.with_url_scope`, `request.scoped_url`, `request.url_for` | Scope applies before public URL emission | Frozen/slotted request scope type | This RFC, routing docs after implementation | Tenant-like example only after API stabilizes | Full page, htmx, redirect, SSE, fragment, no-request tests |
| Fragment composition | No CLI surface | `fragment_url(request.url_for(...), block)` | Current `/_frag{path}?_b={block}` protocol | No new fragment schema | RFC note only until implementation | Shell fixture may use it later | Fragment URL assertion with scoped path |

## 9. Deferred

- `Redirect.to_route(...)` convenience.
- Absolute URL generation with scheme/host.
- `AppConfig` base-path or tenant config.
- Automatic URL rewriting in rendered HTML.
- Product-owned tenant validation, durable tenant lookup, membership, roles, or
  authorization policy.
