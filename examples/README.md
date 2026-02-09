# Chirp Examples

Working examples that demonstrate chirp's core capabilities. Each is self-contained
and runnable — start the dev server or run the tests.

## Examples

### `hello/` — The Basics

Routes, return-value content negotiation, path parameters, Response chaining, error handlers.
No templates. Pure Python. Chirp in ~30 lines.

```bash
cd examples/hello && python app.py
```

### `todo/` — htmx Fragments

The killer feature. A todo list where the same template renders as a full page or a fragment,
depending on whether the request came from htmx. Add, toggle, and delete items with partial
page updates — zero client-side JavaScript. Empty submissions return a `ValidationError`
with a 422 status and an inline error message.

```bash
cd examples/todo && python app.py
```

### `contacts/` — htmx CRUD with Validation

The canonical htmx demo: a contacts list with add, inline edit, delete, and search. Exercises
every htmx ergonomic feature in one app — `ValidationError` for 422 form errors, `OOB` for
multi-fragment updates (table + count badge), `HX-Trigger` for toast notifications on delete,
and `HX-Push-Url` for bookmarkable edit URLs. Tests use all `assert_hx_*` helpers.

```bash
cd examples/contacts && python app.py
```

### `sse/` — Real-Time Events

Server-Sent Events pushing HTML fragments to the browser in real-time. The async generator
yields strings, structured SSEEvent objects, and kida-rendered Fragment objects — demonstrating
all three SSE payload types.

```bash
cd examples/sse && python app.py
```

### `dashboard/` — Full Stack Showcase

The complete Pounce + Chirp + Kida pipeline. A weather station with 6 live sensors:
streaming initial render, fragment caching, SSE-driven updates, and multi-worker
free-threading. Open your browser and watch the data change.

```bash
cd examples/dashboard && python app.py
```

### `hackernews/` — Hacker News Live Reader

A live Hacker News reader consuming the real HN Firebase API. Stories load from the
live API, scores and comment counts update in real-time via SSE, and comment trees
render recursively using kida's `{% def %}`. View Transitions animate between the
story list and detail pages. Zero client-side JavaScript beyond htmx.

```bash
pip install httpx  # or pip install chirp[all]
cd examples/hackernews && python app.py
```

### `rag_demo/` — RAG with Streaming AI Answers

A documentation site with AI-powered Q&A. SQLite stores docs, Claude streams answers
with cited sources. Demonstrates per-worker lifecycle hooks — global `on_startup` for
schema migration, `on_worker_startup` / `on_worker_shutdown` for per-worker database
connections via `ContextVar`. Multi-worker Pounce for free-threading.

```bash
pip install chirp[ai,data]
export ANTHROPIC_API_KEY="sk-..."
cd examples/rag_demo && python app.py
```

### `static_site/` — Static Site Serving with Live Reload

Serves a pre-built static site from a `public/` directory with `StaticFiles` at the root
prefix, custom 404 pages, and `HTMLInject` for injecting a live-reload SSE client into every
HTML response. An SSE endpoint (`/__reload__`) signals the browser when files change. Shows
how chirp can replace a traditional dev server for static site generators.

```bash
cd examples/static_site && python app.py
```

### `auth/` — Session Auth with Protected Routes

The most basic authentication example. A login form, a protected dashboard, and logout.
Hardcoded credentials (`admin` / `password`) with password hashing. Shows the full
`SessionMiddleware` → `AuthMiddleware` → `@login_required` pipeline, `login()` / `logout()`
helpers, `current_user()` in templates, and `hash_password` / `verify_password`.

```bash
cd examples/auth && python app.py
```

### `ollama/` — Local LLM Chat with Ollama

A chat interface powered by a local Ollama instance. Streaming AI responses via SSE,
conversation history, and model selection. Demonstrates real-world LLM integration
without cloud API keys.

```bash
# Requires ollama running locally
cd examples/ollama && python app.py
```

### `signup/` — Registration Form with Validation & CSRF

The chirp forms showcase. A registration form with `validate()` and built-in rules
(`required`, `min_length`, `max_length`, `email`, `matches`), a custom validator
for password confirmation, `CSRFMiddleware` for token protection, and `ValidationError`
for re-rendering with per-field errors. Sessions store the username for the welcome page.

```bash
cd examples/signup && python app.py
```

### `upload/` — Photo Gallery with File Uploads

Multipart form handling from end to end. Upload photos with title and description,
validate file type and size, save to disk with `UploadFile.save()`, and browse the
gallery. Serves uploaded images via `StaticFiles` middleware. Shows `form.files.get()`,
`enctype="multipart/form-data"`, and file metadata (`.filename`, `.content_type`, `.size`).

```bash
pip install chirp[forms]  # python-multipart
cd examples/upload && python app.py
```

### `survey/` — Multi-Field Survey with Checkboxes & Radios

Every HTML form input type in one app. Text, number, checkboxes (`get_list()`), radio
buttons, `<select>`, and `<textarea>`. Validates with `required`, `one_of`, `integer`,
and a custom age-range rule. Demonstrates multi-value field handling — the part of form
parsing that `get()` alone can't cover.

```bash
cd examples/survey && python app.py
```

### `wizard/` — Multi-Step Checkout Form

A 3-step form wizard with session-persisted data: personal info → shipping address →
review & confirm. Each step validates independently with `validate()`, redirects forward
on success, and guards against skipping steps. The review page reads back all collected
data, and confirmation clears the session. Back navigation preserves previously entered values.

```bash
cd examples/wizard && python app.py
```

### `search/` — Book Search with GET Forms & htmx

GET-based forms — no POST, no CSRF. A book catalog with text search, genre filtering, and
sort controls. Uses `request.query` for reading query parameters and `Page` for automatic
full-page vs fragment rendering. htmx drives search-as-you-type with `hx-get`, `hx-push-url`,
and `hx-include` so the URL always reflects the current search state.

```bash
cd examples/search && python app.py
```

## Patterns

Lessons from building these examples — things that aren't bugs but require
intentional decisions from the developer.

### Mark third-party HTML with `| safe`

Kida auto-escapes all template output by default. This is correct — it prevents
XSS. But when you're rendering pre-formatted HTML from an external source (API
responses, CMS content, markdown output), you need to explicitly opt out:

```html
{# Bad: <p> tags rendered as literal &lt;p&gt; text #}
<div class="comment-text">{{ comment.text }}</div>

{# Good: HTML rendered as intended #}
<div class="comment-text">{{ comment.text | safe }}</div>
```

The `| safe` filter accepts an optional `reason=` parameter for documenting why
the content is trusted:

```html
{{ api_html | safe(reason="sanitized by HN API") }}
{{ rendered_md | safe(reason="generated by markdown parser") }}
```

Auto-escaping is a guardrail, not a sharp edge. The `| safe` call is your
declaration that you've thought about trust.

### Use a unique ID for your htmx swap target

When chirp swaps fragments into the page, the `hx-target` selector must resolve
to exactly one element. A class like `.container` is a layout utility that may
appear in headers, footers, and sidebars. Use a unique ID instead:

```html
{# Bad: ambiguous — multiple .container elements on the page #}
<a hx-get="/story/1" hx-target=".container">...</a>

{# Good: one unambiguous target #}
<div id="main" class="container">...</div>
<a hx-get="/story/1" hx-target="#main">...</a>
```

This also matters for View Transitions — `view-transition-name` must be unique
per page. Applying it to a class that matches multiple elements triggers a
browser warning and breaks the transition animation.

```css
/* Bad: every .container gets the same transition name */
.container { view-transition-name: page-content; }

/* Good: only the content area transitions */
#main { view-transition-name: page-content; }
```

ID-based targeting is faster for the browser, unambiguous for htmx, and
compatible with the CSS view-transition-name uniqueness requirement.

## Running Tests

Each example has a `test_app.py` that verifies it works through the ASGI pipeline
using chirp's `TestClient`. No HTTP server required.

```bash
# All examples
pytest examples/

# One example
pytest examples/hello/
```

## What Each Example Exercises

| Feature | hello | todo | contacts | sse | dashboard | hackernews | rag_demo | static_site | auth | signup | upload | survey | wizard | search |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `@app.route()` | x | x | x | x | x | x | x | x | x | x | x | x | x | x |
| Path parameters | x | x | x | | | x | | | | | x | | x | |
| String returns | x | | | | | | | | | | | | | |
| Dict/JSON returns | x | | | | | | | | | | | | | |
| `Response` chaining | x | | | | | | | | | | | | | |
| `@app.error()` | x | | | | | | | | | | | | | |
| `Template` | | x | | x | | x | x | | x | x | x | x | x | |
| `Fragment` | | x | x | x | x | x | x | | | | | | | |
| `Page` | | | x | | | x | | | | | | | | x |
| `ValidationError` | | x | x | | | | | | | x | x | x | x | |
| `OOB` | | | x | | | | | | | | | | | |
| `Stream` | | | | | x | | | | | | | | | |
| `request.is_fragment` | | x | | | | x | | | | | | | | |
| `request.query` | | | | | | | | | | | | | | x |
| `@app.template_filter()` | | x | | | x | x | | | | | x | | | |
| `EventStream` | | | | x | x | x | x | x | | | | | | |
| `SSEEvent` | | | | x | | | | | | | | | | |
| `{% cache %}` | | | | | x | x | | | | | | | | |
| `hx-swap-oob` | | | x | | x | x | | | | | | | | |
| `with_hx_*()` headers | | | x | | | | | | | | | | | |
| `assert_hx_*` test helpers | | | x | | | | | | | | | | | |
| Multi-worker Pounce | | | | | x | x | x | | | | | | | |
| `TestClient.fragment()` | | x | | | | x | | | | | | | | x |
| `TestClient.sse()` | | | | x | x | x | | x | | | | | | |
| `@app.on_startup` | | | | | | x | x | | | | | | | |
| `@app.on_worker_startup` | | | | | | x | x | | | | | | | |
| `@app.on_worker_shutdown` | | | | | | x | x | | | | | | | |
| `httpx` (real API) | | | | | | x | | | | | | | | |
| `chirp.data` (SQLite) | | | | | | | x | | | | | | | |
| `chirp.ai` (LLM streaming) | | | | | | | x | | | | | | | |
| `ContextVar` per-worker | | | | | | x | x | | | | | | | |
| Recursive `{% def %}` | | | | | | x | | | | | | | | |
| View Transitions | | | | | | x | | | | | | | | |
| `StaticFiles` (root prefix) | | | | | | | | x | | | x | | | |
| `HTMLInject` | | | | | | | | x | | | | | | |
| Custom 404 page | | | | | | | | x | | | | | | |
| `SessionMiddleware` | | | | | | | | | x | x | | | x | |
| `AuthMiddleware` | | | | | | | | | x | | | | | |
| `@login_required` | | | | | | | | | x | | | | | |
| `login()` / `logout()` | | | | | | | | | x | | | | | |
| `current_user()` template global | | | | | | | | | x | | | | | |
| `hash_password` / `verify_password` | | | | | | | | | x | | | | | |
| `Redirect` | | | | | | | | | x | x | x | | x | |
| `validate()` + built-in rules | | | | | | | | | | x | x | x | x | |
| `CSRFMiddleware` + `csrf_field()` | | | | | | | | | | x | x | | | |
| `UploadFile` / multipart | | | | | | | | | | | x | | | |
| `form.files` / `file.save()` | | | | | | | | | | | x | | | |
| `form.get_list()` (multi-value) | | | | | | | | | | | | x | | |
| `one_of` validator | | | | | | | | | | | | x | | |
| `integer` / `number` validator | | | | | | | | | | | | x | | |
| `matches` validator | | | | | | | | | | x | | | x | |
| Session-persisted form flow | | | | | | | | | | | | | x | |
| `get_session()` | | | | | | | | | | x | | | x | |
| GET query-param forms | | | | | | | | | | | | | | x |
| `hx-push-url` search | | | | | | | | | | | | | | x |
