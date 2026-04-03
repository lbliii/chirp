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

### Validation pattern
```python
result = validate(form_data, RULES)
if not result:
    return ValidationError("page.html", "form_block", errors=result.errors, form=values)
```

## Code Style

- **Frozen dataclasses** for models and config (thread-safe, immutable)
- **ContextVar** for request-scoped state (`g`, `get_request()`)
- **Protocol-based middleware** (no base class, just match the signature)
- **Thread-safe stores** with `threading.Lock` for shared mutable state
- **`app.check()`** validates hypermedia contracts at startup (routes, fragments, SSE)

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
`AlpineInject` middleware appends the Alpine script before `</body>` on full-page
HTML responses. Dedup: if `data-chirp="alpine"` already exists in the body, injection
is skipped.

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

## Dependencies

Core: `kida-templates`, `anyio`, `bengal-pounce`. Everything else optional:
- `chirp[forms]` — python-multipart for file uploads
- `chirp[markdown]` — patitas for markdown rendering
- `chirp[all]` — everything including httpx
