# RFC 006: Request URL Scope For Tenant And Base-Path Apps

**Status:** Draft
**Author:** (proposal)
**Created:** 2026-05-09
**Depends on:** RFC 003 (named routes), RFC 004 (`url_for`)

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

The exact storage API is still open, but it must not require consumers to write
to `request._cache`. Candidate shapes:

```python
scoped_request = request.with_url_scope(RequestUrlScope(prefix="/c/acme"))
request.url_scope
```

or:

```python
with request_url_scope("/c/acme"):
    ...
```

The request-object shape is preferred because it composes with explicit
middleware and keeps scope visible in tests.

### 3.2 Scoped URL Helpers

Keep `app.url_for(...)` unchanged. Add request-aware composition points:

```python
request.url_for("boards.detail", board_slug="ic")
# -> "/c/acme/boards/ic" when the request has prefix="/c/acme"

request.scoped_url(app.url_for("boards.detail", board_slug="ic"))
# -> same result, useful for redirects and existing helpers
```

Templates should receive a request-aware `url_for` only when rendering inside a
request. This must keep `setdefault` semantics from RFC 004: user-defined
template globals still win.

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

If that shape conflicts with the current fragment dispatcher, the RFC must
settle it before implementation. An alternative is a query field that stores
the scoped public path while the dispatcher still routes against the local app
path.

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

## 6. Required Proof Before Implementation

- `tests/test_url_for.py` keeps all existing app-root assertions.
- New tests cover:
  - request-scoped `url_for` in a full-page render;
  - boosted htmx link generation;
  - `Redirect` built from `request.scoped_url(...)`;
  - query-string `next` preservation;
  - SSE endpoint attribute generation;
  - no ambient prefix in background/template renders without a request.
- Browser smoke for one shell example if the implementation changes htmx
  navigation behavior.
- `app.check()` remains deterministic without a request scope.

---

## 7. Open Questions

- Should the first public API be `request.url_for(...)`, `request.scoped_url(...)`,
  both, or a standalone helper?
- Should scoped fragment URLs route through the existing `/_frag/<path>` shape
  or a query-encoded local path?
- Should `Redirect.to_route(...)` exist, or is explicit `Redirect(request.url_for(...))`
  clear enough?
- Can template request-aware `url_for` be injected without making background
  template renders surprising?
