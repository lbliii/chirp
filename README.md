# ⌁⌁ Chirp

[![PyPI version](https://img.shields.io/pypi/v/bengal-chirp.svg)](https://pypi.org/project/bengal-chirp/)
[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://pypi.org/project/bengal-chirp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Status: Alpha](https://img.shields.io/badge/status-alpha-orange.svg)](https://pypi.org/project/bengal-chirp/)

**A Python web framework for HTMX, HTML fragments, streaming HTML, and Server-Sent Events.**

```python
from chirp import App

app = App()

@app.route("/")
def index():
    return "Hello, World!"

app.run()
```

---

## What is Chirp?

Chirp is a Python web framework built for the modern web platform: browser-native UI, HTML over the wire, streaming responses, and Server-Sent Events. Routes return intent — `Page`, `Fragment`, `OOB`, `EventStream`, `Suspense` — and the framework handles content negotiation, layout composition, and htmx awareness automatically. One template with named blocks serves as a full page, a fragment endpoint, an SSE payload, and a Suspense deferred block. No `make_response()`. No `jsonify()`. The type *is* the intent.

```python
@app.route("/search")
async def search(request: Request):
    results = await db.search(request.query.get("q", ""))
    return Page("search.html", "results", results=results)
    # Full page for browsers. Fragment for htmx. Same template, same data.
```

- **Browser-native UI** — `<dialog>`, `popover`, View Transitions, container queries. Let the browser be the framework.
- **HTML over the wire** — Full pages, fragments, streaming HTML, and SSE. Built for htmx.
- **Streaming HTML** — Shell first, content fills in as data arrives. No loading spinners.
- **Server-Sent Events** — Real-time updates over plain HTTP. No WebSocket upgrade required.
- **MCP tools** — Register functions as tools callable by LLMs and MCP clients.

Read the [Philosophy](docs/philosophy.md) for the full picture.

## Use Chirp For

- **HTMX-driven web apps** — Server-rendered UI with fragment swaps and progressive enhancement
- **Server-rendered applications** — Full pages plus partial updates from the same templates
- **Streaming interfaces** — Progressive HTML delivery and token-by-token responses
- **Real-time dashboards** — SSE-powered updates without WebSocket complexity
- **Teams avoiding heavy frontend stacks** — HTML, CSS, templates, and browser-native features

---

## Installation

```bash
# pip
pip install bengal-chirp

# uv
uv add bengal-chirp
```

Requires Python 3.14+.

Chirp works on its own with plain templates. `chirp-ui` is an optional companion UI layer, not part of the framework core.

---

## Quick Start

```bash
chirp new myapp && cd myapp && python app.py
```

| Function | Description |
|----------|-------------|
| `chirp new <name>` | Scaffold an auth-ready project |
| `chirp new <name> --shell` | Scaffold with a persistent app shell (topbar + sidebar) |
| `chirp new <name> --sse` | Scaffold with SSE boilerplate (`EventStream`, `sse_scope`) |
| `chirp run <app>` | Start the dev server from an import string |
| `chirp check <app>` | Validate hypermedia contracts |
| `chirp check <app> --warnings-as-errors` | Fail CI on contract warnings |
| `chirp routes <app>` | Print the registered route table |
| `App()` | Create an application |
| `@app.route(path)` | Register a route handler |
| `Template(name, **ctx)` | Render a full template |
| `Template.inline(src, **ctx)` | Render from string (prototyping) |
| `Page(name, block, **ctx)` | Auto Fragment or Template based on request |
| `PageComposition(template, fragment_block, ...)` | Python-first composition with regions |
| `Fragment(name, block, **ctx)` | Render a named template block |
| `Stream(name, **ctx)` | Stream HTML progressively |
| `Suspense(name, **ctx)` | Shell first, OOB swaps for deferred data |
| `EventStream(gen)` | Server-Sent Events stream |
| `hx_redirect(url)` | Redirect helper for htmx and full-page requests |
| `app.run()` | Start the development server |

---

## Features

| Feature | Description | Docs |
|---------|-------------|------|
| **HTMX Patterns** | Search, inline edit, infinite scroll, modal, and fragment workflows | [htmx Patterns →](https://lbliii.github.io/chirp/docs/tutorials/htmx-patterns/) |
| **Comparison** | When Chirp fits compared with Flask, FastAPI, and Django | [When to Use Chirp →](https://lbliii.github.io/chirp/docs/about/comparison/) |
| **Routing** | Pattern matching, path params, method dispatch | [Routing →](https://lbliii.github.io/chirp/docs/routing/) |
| **Filesystem routing** | Route discovery from `pages/` with layouts | [Filesystem →](https://lbliii.github.io/chirp/docs/routing/filesystem-routing/) |
| **Route directory contract** | `_meta.py`, `_context.py`, `_actions.py`, sections, shell context, and route validation | [Route Directory →](https://lbliii.github.io/chirp/docs/guides/route-directory/) |
| **Route introspection** | Reserved files, inheritance rules, debug headers, and route explorer | [Route Contract →](https://lbliii.github.io/chirp/docs/reference/route-contract/) |
| **Templates** | Kida integration, rendering, filters | [Templates →](https://lbliii.github.io/chirp/docs/templates/) |
| **Fragments** | Render named template blocks independently | [Fragments →](https://lbliii.github.io/chirp/docs/templates/fragments/) |
| **Forms** | `form_or_errors`, form macros, validation | [Forms →](https://lbliii.github.io/chirp/docs/data/forms-validation/) |
| **Streaming** | Progressive HTML rendering via Kida | [Streaming →](https://lbliii.github.io/chirp/docs/streaming/) |
| **SSE** | Server-Sent Events for real-time updates | [SSE →](https://lbliii.github.io/chirp/docs/streaming/server-sent-events/) |
| **Middleware** | CORS, sessions, static files, security headers, custom | [Middleware →](https://lbliii.github.io/chirp/docs/middleware/) |
| **Contracts** | Validate htmx attrs, form actions, and route-bearing dialog args | [Reference →](https://lbliii.github.io/chirp/docs/reference/) |
| **Testing** | Test client, assertions, isolation utilities | [Testing →](https://lbliii.github.io/chirp/docs/testing/) |
| **Data** | Database integration and form validation | [Data →](https://lbliii.github.io/chirp/docs/data/) |
| **Optional UI layer** | `chirp-ui` companion components and styles | [chirp-ui →](https://github.com/lbliii/chirp-ui) |

📚 **Full documentation**: [lbliii.github.io/chirp](https://lbliii.github.io/chirp/)

---

## Benchmarks

Chirp now ships a synthetic benchmark suite for comparing Chirp, FastAPI, and Flask across JSON and CPU workloads, plus Chirp-specific fused sync and mixed JSON+SSE scenarios.

```bash
uv sync --extra benchmark
uv run poe benchmark
```

See [`benchmarks/README.md`](benchmarks/README.md) for how the benchmarks work, their caveats, and the available runners.

---

## Production Deployment

Chirp apps run on **[Pounce](https://github.com/lbliii/pounce)**, a production-grade ASGI server with HTTP/2, graceful shutdown, Prometheus metrics, rate limiting, and multi-worker scaling. See the [deployment guide](https://lbliii.github.io/chirp/docs/deployment/production/) for details.

---

## Usage

<details>
<summary><strong>Return Values</strong> — Type-driven content negotiation</summary>

Route functions return *values*. The framework handles content negotiation based on the type:

```python
return "Hello"                                  # -> 200, text/html
return {"users": [...]}                         # -> 200, application/json
return Template("page.html", title="Home")      # -> 200, rendered via Kida
return Page("search.html", "results", items=x)  # -> Fragment or Template (auto)
return Fragment("page.html", "results", items=x) # -> 200, rendered block
return Stream("dashboard.html", **async_ctx)    # -> 200, streamed HTML
return Suspense("dashboard.html", stats=...)    # -> shell + OOB swaps
return EventStream(generator())                 # -> SSE stream
return hx_redirect("/dashboard")                # -> Location + HX-Redirect
return Response(body=b"...", status=201)         # -> explicit control
return Redirect("/login")                       # -> 302
```

No `make_response()`. No `jsonify()`. The type *is* the intent.

For htmx-driven form posts or mutations that should trigger a full-page
navigation, prefer `hx_redirect()` so both plain browser and htmx requests
follow the redirect correctly.

</details>

<details>
<summary><strong>Fragments and htmx</strong> — Render template blocks independently</summary>

Kida can render a named block from a template independently, without rendering the whole page:

```html
{# templates/search.html #}
{% extends "base.html" %}

{% block content %}
  <input type="search" hx-get="/search" hx-target="#results" name="q">
  {% block results_list %}
    <div id="results">
      {% for item in results %}
        <div class="result">{{ item.title }}</div>
      {% end %}
    </div>
  {% endblock %}
{% endblock %}
```

```python
@app.route("/search")
async def search(request: Request):
    results = await db.search(request.query.get("q", ""))
    if request.is_fragment:
        return Fragment("search.html", "results_list", results=results)
    return Template("search.html", results=results)
```

Full page request renders everything. htmx request renders just the `results_list` block.
Same template, same data, different scope. No separate "partials" directory.

</details>

<details>
<summary><strong>Streaming HTML</strong> — Progressive rendering</summary>

Kida renders template sections as they complete. The browser receives the shell immediately
and content fills in progressively:

```python
@app.route("/dashboard")
async def dashboard(request: Request):
    return Stream("dashboard.html",
        header=site_header(),
        stats=await load_stats(),
        activity=await load_activity(),
    )
```

</details>

<details>
<summary><strong>Server-Sent Events</strong> — Real-time HTML updates</summary>

Push Kida-rendered HTML fragments to the browser in real-time:

```python
@app.route("/notifications")
async def notifications(request: Request):
    async def stream():
        async for event in notification_bus.subscribe(request.user):
            yield Fragment("components/notification.html", event=event)
    return EventStream(stream())
```

Combined with htmx's SSE support, this enables real-time UI updates with zero client-side
JavaScript. The server renders HTML, the browser swaps it in.

</details>

<details>
<summary><strong>Middleware</strong> — Composable request/response pipeline</summary>

No base class. No inheritance. A middleware is anything that matches the protocol:

```python
async def timing(request: Request, next: Next) -> Response:
    start = time.monotonic()
    response = await next(request)
    elapsed = time.monotonic() - start
    return response.with_header("X-Time", f"{elapsed:.3f}")

app.add_middleware(timing)
```

Built-in middleware: CORS, StaticFiles, HTMLInject, Sessions, SecurityHeaders.

</details>

<details>
<summary><strong>Typed Contracts</strong> — Compile-time hypermedia validation</summary>

Chirp validates the server-client boundary at startup:

```python
# Prints a contract report and exits non-zero on errors.
app.check()

# Optional strict mode: treat warnings as failures too.
app.check(warnings_as_errors=True)
```

Every `hx-get`, `hx-post`, and `action` attribute in your templates is checked against the
registered route table. Every `Fragment` and `SSE` return type is checked against available
template blocks. SSE safety checks catch broken `sse-connect` / `sse-swap` structures and
unsafe inherited target scopes before runtime.

For strict CI:

```bash
chirp check myapp:app --warnings-as-errors
```

</details>

---

## Development

```bash
git clone https://github.com/lbliii/chirp.git
cd chirp
uv sync --group dev
pytest
```

---

## The Bengal Ecosystem

A structured reactive stack written in pure Python for 3.14t free-threading. Chirp is the framework; packages like `chirp-ui` sit on top as optional companions.

| | | | |
|--:|---|---|---|
| **ᓚᘏᗢ** | [Bengal](https://github.com/lbliii/bengal) | Static site generator | [Docs](https://lbliii.github.io/bengal/) |
| **∿∿** | [Purr](https://github.com/lbliii/purr) | Content runtime | — |
| **⌁⌁** | **Chirp** | Web framework ← You are here | [Docs](https://lbliii.github.io/chirp/) |
| **ʘ** | [chirp-ui](https://github.com/lbliii/chirp-ui) | Optional companion UI layer | — |
| **=^..^=** | [Pounce](https://github.com/lbliii/pounce) | ASGI server | [Docs](https://lbliii.github.io/pounce/) |
| **)彡** | [Kida](https://github.com/lbliii/kida) | Template engine | [Docs](https://lbliii.github.io/kida/) |
| **ฅᨐฅ** | [Patitas](https://github.com/lbliii/patitas) | Markdown parser | [Docs](https://lbliii.github.io/patitas/) |
| **⌾⌾⌾** | [Rosettes](https://github.com/lbliii/rosettes) | Syntax highlighter | [Docs](https://lbliii.github.io/rosettes/) |

Python-native. Free-threading ready. No npm required.

---

## License

MIT
