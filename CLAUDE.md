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

### Suspense (deferred blocks)
```python
return Suspense("page.html",
    title="Dashboard",       # sync — in the shell
    stats=load_stats(),      # awaitable — deferred
    feed=load_feed(),        # awaitable — deferred
)
```

Awaitable context values are deferred: the shell renders with those keys set to `None`
(showing skeleton/fallback content). The shell also sets `__chirp_defer_pending__` to a
`frozenset` of deferred key names (`CHIRP_DEFER_PENDING_KEY`); deferred block re-renders
use an empty frozenset. In templates use **`{% if key is not none %}`** (or
`"key" in __chirp_defer_pending__`) for loading vs loaded — not bare **`{% if key %}`**,
which is falsy for empty `tuple`/`list`/`""`/`0` after resolution. Then each affected
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
- **`app.check()`** validates hypermedia contracts at startup (routes, fragments, SSE)
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
```

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

## Dependencies

Core: `kida-templates`, `anyio`, `bengal-pounce`. Everything else optional:
- `chirp[forms]` — python-multipart for file uploads
- `chirp[markdown]` — patitas for markdown rendering
- `chirp[all]` — everything including httpx
