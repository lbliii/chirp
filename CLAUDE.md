# Chirp — Development Guide

## What is Chirp?

Chirp is a Python web framework for hypermedia-native applications. It serves HTML — full pages, fragments, streaming responses, and Server-Sent Events — using return types to express intent. The framework handles content negotiation, layout composition, and htmx awareness automatically.

## Architecture: Intent-Driven Responses

The core design principle: **the return type is the intent**. Routes return values, not response objects.

```python
return Template("page.html", **ctx)       # Full page render
return Fragment("page.html", "block")     # Named block only
return Page("page.html", "block", **ctx)  # Auto: fragment for htmx, full page for browsers
return OOB(main, *oob_fragments)          # Multi-target swap
return EventStream(async_generator)       # SSE stream
return Suspense("page.html", **ctx)       # Shell first, deferred blocks stream in
return Suspense("page.html", defer_blocks=("stats", "feed"), **ctx)  # Explicit OOB targets
return ValidationError("page.html", "form", errors=e)  # 422 + re-rendered form
return FormAction(redirect, *fragments)   # Fragments for htmx, redirect for plain POST
```

No `make_response()`. No `jsonify()`. The type drives everything.

## One Template, Many Modes

A single template with named blocks serves as:
- A full page (browser navigation)
- A fragment endpoint (htmx swap via `Fragment`)
- An SSE payload (`EventStream` yields `Fragment`)
- A Suspense deferred block (resolved after shell renders)

No separate partials directory. No API serialization layer.

## Project Structure

### Standalone apps (simple)
```
app.py              # Routes, middleware, app setup
templates/          # Kida templates
static/             # CSS, images
```

### Mounted pages (filesystem routing)
```
app.py
pages/
  _layout.html      # Root layout
  _context.py       # Root context provider (inherits down)
  _meta.py          # Route metadata (title, breadcrumbs, auth)
  _actions.py       # Named form actions
  page.py           # GET / handler
  page.html         # Template
  contacts/
    page.py          # GET /contacts
    page.html
    _context.py      # Scoped context (merges with parent)
    {contact_id}/
      page.py        # GET /contacts/{id}
      page.html
```

**Composition model:** Layouts and page templates use **composition**, not inheritance. Chirp injects page HTML into the layout's `{% block content %}` via `render_with_blocks`. Page templates **cannot** override sibling layout blocks like `page_scripts` or `head_extra` — those are only available to templates that `{% extends %}` the layout directly. If a page needs an inline `<script>`, put it inside the content region (inside `page_root` or `page_content`).

## Key Patterns

### Fragment + OOB for mutations
```python
@app.route("/save", methods=["POST"])
async def save(request: Request):
    # ... update data ...
    return OOB(
        Fragment("page.html", "item_row", item=updated),
        Fragment("page.html", "item_count", target="count", count=n),
    )
```

### SSE for real-time
```python
@app.route("/events", referenced=True)
def events():
    async def generate():
        while True:
            data = await wait_for_change()
            yield Fragment("page.html", "live_block", data=data)
    return EventStream(generate())
```

### Streaming types — pick the right one

| Type | Shell first? | Transport | Use when | Don't use for |
|------|--------------|-----------|----------|---------------|
| `Stream` | No — flush blocks as they complete | Single chunked HTTP response | Slow first-byte pages where independent sections can paint progressively (SEO-friendly streaming render) | Updates after the page has loaded; long-lived connections |
| `Suspense` | Yes — shell renders first with `None` placeholders, then deferred blocks stream as OOB swaps | Single chunked HTTP response (htmx OOB chunks fill placeholders) | Dashboards / detail pages with multiple slow data sources where you want one round trip and an instant shell | Post-load updates; cross-tab fan-out |
| `EventStream` | N/A — pure event channel, no shell | SSE (`text/event-stream`, long-lived) | Realtime updates *after* the page is loaded (notifications, ticker, chat tail, live dashboards) | Initial page render; one-shot data fetches |

If you're not sure: a one-shot dashboard that loads slow data → `Suspense`. A
notifications feed that updates after the page loads → `EventStream`. A page
where the *first* paint streams in section-by-section → `Stream`.

### Request context in streamed renders

`Suspense`, `Stream`, and `EventStream` generators run *after* the handler's
`finally` has reset the request ContextVars, so Chirp captures the request +
auth user + CSRF token + `g` (and CSP nonce) at construction/negotiation time
and re-establishes them for the drain. Inside a deferred block, a `Stream`
generator, or an SSE generator, `get_request()`, `get_user()` /
`current_user()`, `get_csrf_token()`, and `g` all work — they return the values
that were live in the handler.

**SSE identity is pinned at connect time.** The snapshot is fixed for the life
of the SSE connection: a user logged out or permission-revoked mid-stream keeps
the connect-time identity until they reconnect. Call ``app.kick_user(user_id)``
to terminate that user's live streams so htmx reconnect re-runs auth middleware
and re-pins fresh permissions. The SSE session is a **read-only connect-time snapshot** —
there is no response to write `Set-Cookie`, so session mutations inside an SSE
generator do not persist. `g` writes inside a deferred block / generator are
local to that render and do not flow back to the (already-completed) handler.

Two `app.check()` rules guard SSE user reads (see `rules_sse.py`):
`sse_auth_gate` (env-aware ERROR prod / WARNING staging / silent dev) flags an
`EventStream` generator that reads `get_user()`/`current_user()` with **no
`AuthMiddleware`** wired — the captured user would be `AnonymousUser` for the
whole stream. `sse_context` is a low-severity (WARNING, never ERROR) **semantic
nudge** surfacing the connect-time-pinning caveat when the user is read inside a
long-lived SSE loop. Both statically resolve only **inline** and **module-level**
generators (the latter via the handler `__globals__`); a generator built by any
other indirection is silently skipped (documented blind spot, never a false
ERROR).

### Suspense (deferred blocks)
```python
return Suspense("page.html",
    title="Dashboard",       # sync — in the shell
    stats=load_stats(),      # awaitable — deferred
    feed=load_feed(),        # awaitable — deferred
)
```

Awaitable context values are deferred: the shell renders with those keys set to the
`DEFERRED` sentinel (showing skeleton/fallback content). The shell also sets
`__chirp_defer_pending__` to a `frozenset` of deferred key names
(`CHIRP_DEFER_PENDING_KEY`); deferred block re-renders use an empty frozenset. In
templates use **`{% if key is deferred %}`** (or `"key" in __chirp_defer_pending__`) for
loading vs loaded — not bare **`{% if key %}`**, which is falsy for empty
`tuple`/`list`/`""`/`0` after resolution. Then each affected
block is re-rendered and streamed as an OOB swap.

Blocks to re-render are discovered automatically via `block_metadata().depends_on`.
Ancestor blocks whose `depends_on` is a strict superset of leaf blocks are pruned
(they would produce wasteful OOB chunks targeting non-existent DOM ids).

When static analysis misses blocks (e.g. deferred values passed through macro args),
use `defer_blocks` to bypass discovery:

```python
return Suspense("page.html",
    defer_blocks=("hero_stats", "sidebar_stats"),
    stats=load_stats(),
)
```

`defer_map` remaps block names to DOM ids for the OOB swap target:

```python
return Suspense("page.html",
    defer_map={"stats": "stats-panel"},
    stats=load_stats(),
)
```

### Validation pattern
```python
result = validate(form_data, RULES)
if not result:
    return ValidationError("page.html", "form_block", errors=result.errors, form=values)
```

### OOB fail-loud policy

Region updates (shell OOB swaps, Suspense deferred blocks) **must** resolve to a
block that exists in the target template. Missing blocks raise
`chirp.errors.BlockNotFoundError` rather than emitting empty swaps that would
silently wipe live DOM content. Use `optional=True` only when the region is
legitimately absent from some layouts (e.g. shell regions for apps without
`chirp-ui`):

```python
app.register_oob_region(
    "breadcrumbs_oob",
    target_id="chirpui-topbar-breadcrumbs",
    optional=True,   # silent-skip when layout does not define this block
)
```

`app.check()` enforces this at startup via the `oob_registry` category: ERROR
for non-optional orphans, WARNING for optional orphans. Do not use
`optional=True` to paper over typos — fix the layout or the registration.
`BlockNotFoundError` multi-inherits from `KeyError` for back-compat with existing
`except KeyError` handlers. See `docs/guides/oob-registry.md`.

## Code Style

- **Frozen dataclasses** for models and config (thread-safe, immutable)
- **ContextVar** for request-scoped state (`g`, `get_request()`)
- **Protocol-based middleware** (no base class, just match the signature)
- **Thread-safe stores** with `threading.Lock` for shared mutable state
- **`app.check()`** validates hypermedia contracts at startup (routes, fragments, SSE). In debug mode this runs automatically on `app.run()`/`app.freeze()` and exits on ERROR. Opt out via `AppConfig(skip_contract_checks=True)` or `CHIRP_SKIP_CONTRACT_CHECKS=1`.
- **Python 3.14 except syntax**: `except ValueError, TypeError:` is the canonical form (ruff-normalized). Do **not** add parens — this is valid 3.14+ syntax, not a Python 2 holdover.

## Custom Contract Checks

Third-party packages and apps can extend `app.check()` with custom validation rules.

### Registering checks

```python
from chirp import ContractCheck, ContractCheckSnapshot, CheckResult, ContractIssue, Severity

def my_check(snapshot: ContractCheckSnapshot, result: CheckResult) -> None:
    for name, source in snapshot.template_sources.items():
        if "TODO" in source:
            result.issues.append(
                ContractIssue(Severity.WARNING, "todo", f"TODO in {name}", template=name)
            )

app.register_contract_check(my_check)
```

- Checks receive a frozen `ContractCheckSnapshot` and a mutable `CheckResult`
- Both function and callable class forms are accepted (`ContractCheck` Protocol)
- Register during setup (before freeze); raises `RuntimeError` after freeze
- Exceptions in checks are isolated — they become ERROR issues, other checks still run
- Checks run in registration order, after all built-in rules

### Passing data to checks

```python
app.set_contract_check_data("components", ["card", "modal"])

def my_check(snapshot, result):
    components = snapshot.extras["components"]  # → ["card", "modal"]
```

### Severity overrides

```python
app.override_contract_severity("dead", Severity.ERROR)    # Promote dead-template INFO → ERROR
app.override_contract_severity("orphan", Severity.WARNING) # Promote orphan-route INFO → WARNING
```

Overrides apply as post-processing after all checks run. Any category (built-in or custom) can be overridden.

### Plugin convention

Packages should register checks inside their `register()` or setup function — no magic discovery. See `chirp.ext.chirp_ui` for a real-world example (validates component imports).

## Build & Test

```bash
uv sync --group dev          # Install deps
uv run pytest                # Run tests
uv run ruff check .          # Lint
uv run ruff format . --check # Format check
uv run poe preflight         # Fast pre-push invariants (lint + format + ty + API/docs snapshot tests)
```

`poe preflight` (alias `make preflight`) runs only the cheap whole-repo
invariants — `ruff check`, `ruff format --check`, `ty check src/chirp/`, and the
two repo-wide invariant tests (`tests/test_lazy_imports.py`,
`tests/test_public_api_docs.py`) — and exits non-zero on the first failure. It
does **not** run the full pytest suite, so it finishes in seconds and catches
the public-API-snapshot / docs-coverage / format / ty failure class locally
before a push instead of via a ~20-minute CI round-trip. Run it before pushing
(it is also wired as a `pre-push` hook in `.pre-commit-config.yaml`).

## Configuration

`AppConfig` is a frozen dataclass. Key fields:
- `template_dir` — path to templates
- `debug` — enables dev tools, error pages, hot reload
- `worker_mode` — `"async"` for SSE/streaming, `"sync+thread"` for simple apps
- `view_transitions` — `False` (off), `True`/`"htmx"` (swap animations), `"full"` (MPA + htmx)
- `secret_key` — required for sessions, CSRF

## Alpine.js Injection

Chirp is the **single authority** for Alpine.js. When `AppConfig(alpine=True)`,
`AlpineInject` middleware appends the Alpine script before `</body>` on buffered
full-page HTML and rewrites **`StreamingResponse`** chunk streams the same way (e.g.
`Suspense` shells). Dedup: if `data-chirp="alpine"` already exists before `</body>`,
injection is skipped.

### CDN URL footgun

All jsDelivr script URLs **must** use explicit `/dist/cdn.min.js` paths.
A bare `https://cdn.jsdelivr.net/npm/alpinejs@3.15.8` (no `/dist/...`) resolves to
`dist/module.cjs.js` (CommonJS), which throws `ReferenceError: module is not defined`
in the browser. This is silent — the error shows only as `"Script error."` due to CORS.

```python
# WRONG — bare path → CJS module → broken in browser
f"https://cdn.jsdelivr.net/npm/alpinejs@{version}"

# CORRECT — explicit browser CDN build
f"https://cdn.jsdelivr.net/npm/alpinejs@{version}/dist/cdn.min.js"
```

Scoped plugins must use the same pattern, for example
`https://cdn.jsdelivr.net/npm/@alpinejs/mask@{version}/dist/cdn.min.js`.

**Symptoms:** All Alpine-powered components dead (toggles, dropdowns, modals,
command palette, sidebar collapse). `window.Alpine` is `undefined`. No visible
JS errors in console (CORS masks cross-origin script errors).

**Diagnosis:** Check the Alpine `<script>` tag's `src` attribute in the browser
inspector. If it ends with `@3.x.x` without `/dist/cdn.min.js`, that's the bug.

Tests in `tests/test_alpine.py` enforce this — `test_no_bare_package_urls` will
catch any regression.

### `alpine_json_config` (template global)

When `alpine=True`, Kida templates can emit a JSON config bridge with
`{{ alpine_json_config("my-id", data) }}` — a `<script id="my-id" type="application/json">`
tag with HTML-escaped ids and `json.dumps(..., default=str)` for the payload
(see `site/content/docs/guides/alpine.md`.)
The global is not registered when `alpine=False`.

## Secure by Default

Chirp does **not** force-inject security middleware into `App()`
(explicit-over-magic). The lever is the `security_stack` contract plus scaffold
defaults. An app with any **mutating route** — POST/PUT/PATCH/DELETE handlers,
*and* filesystem pages that ship `_actions.py` form actions (a GET-only `page.py`
that mutates via POST-to-self on the `_action` field — Chirp does *not* register a
separate POST route, so the page is detected via its non-empty `actions`) — must
wire the secure-by-default stack: `SessionMiddleware` → `CSRFMiddleware` →
`SecurityHeadersMiddleware`.

`security_stack` is the canonical owner of the "mutating route" definition
(`MUTATING_METHODS` / `is_mutating_route` in
`src/chirp/contracts/rules_security_stack.py`; `rules_nojs_floor` imports it).
Severity is env-aware: missing CSRF/Session is **ERROR in production, WARNING in
staging, silent in development**; missing SecurityHeaders is always **WARNING**.
`csrf_session` checks stack ordering; `csrf_form` checks template `<form>` tags;
`security_stack` is the route-level presence check.

Every `chirp new` scaffold — including `--minimal` — wires this stack and reads
the secret key from `CHIRP_SECRET_KEY`, so generated apps pass the contract out
of the box. See `src/chirp/cli/templates/minimal.py` and
`site/content/docs/quality/contracts-debugging/categories.md`.

### Declarative auth (`RouteMeta.auth` / `AuthSpec`)

Filesystem pages gate via `RouteMeta.auth` (in `_meta.py`), enforced by the same
shared core (`chirp.security.auth_core.enforce_auth`) as the imperative
`@login_required` / `@requires` decorators — identical 302/401/403 outcomes and
identical `emit_security_event` audit payloads. `auth` is `str | AuthSpec | None`:

- `None`/`"none"`/`"optional"`/`""` open; `"required"` authn-only; any other
  string a single required permission (back-compat, exact runtime meaning
  preserved by `normalize_auth_spec`).
- `AuthSpec(permissions=(...), mode="all"|"any", policy=<name>, scopes=(...))`
  for permission sets, named policies, and machine-token scopes. There is **no
  `required` flag** — an `AuthSpec` always requires authentication, so
  `AuthSpec()` is authn-only. `AuthSpec` is **static serializable data** —
  `policy` is a string NAME, never a live `Callable`. `AuthSpec` lives in
  `chirp.pages.types` (symmetry with `RouteMeta`; not a top-level export).

`scopes` is the **machine-auth** axis, distinct from human `permissions`:
webhook/cron/provisioning endpoints gate on a token-resolved client's scopes (a
`chirp.middleware.auth.ClientWithScopes` / `MachineClient` exposing `scopes:
frozenset[str]`, module-level not top-level). A client with the scope but no
permissions passes; a user with permissions but not the scope fails the scope
gate. Scope enforcement is **implicitly off** when a spec declares no scopes (no
enable flag). Scope-name equality uses `secrets.compare_digest` (constant-time).

`auth` is normalized to a canonical `AuthSpec | None` at **discovery time** (and
for dynamic `meta()` results at request time) so the per-request gate is
allocation-free and reserved-token confusion fails loud at startup. A `dict` auth
value (`{"permissions": ["a"], "mode": "any"}` / `{"scopes": ["webhook:write"]}`)
constructs an `AuthSpec`; static `META` and dynamic `meta()` parse `auth` through
one shared `dict_to_route_meta` / `normalize_route_meta` helper
(`chirp/pages/discovery.py`).

Three App registries (before-freeze only, raise `RuntimeError` after freeze):

- `app.register_permission(name, *, description=None)` — declares a permission.
- `app.register_policy(name, fn)` — registers a `(user, request) -> bool`
  callable; the declarative gate resolves an `AuthSpec.policy` NAME against it at
  request time. An unregistered policy name fails loud (500).
- `app.register_scope(name, *, description=None)` — declares a machine-token
  scope (the machine-auth axis).

The `auth_spec` contract check is **registry-backed** when
permissions/policies/scopes are declared (unknown permission/policy/scope →
env-aware ERROR); with no registry it falls back to the high-signal
reserved-token-typo heuristic for permissions. A scope denial emits the canonical
`authz.scope.denied` event (distinct from `authz.permission.denied`). See
`src/chirp/contracts/rules_auth_meta.py` and `src/chirp/security/AGENTS.md`.

## Dependencies

Core: `kida-templates`, `anyio`, `bengal-pounce`. Everything else optional:
- `chirp[forms]` — python-multipart for file uploads
- `chirp[markdown]` — patitas for markdown rendering
- `chirp[all]` — everything including httpx

## GitHub Issues (agents)

Do **not** implement issues labeled `good first issue` or titled `[GF] ...`.
Those are reserved for external contributors. See root `AGENTS.md` § GitHub
Issues. Epic #446 and children #447–#458 are all GF.
