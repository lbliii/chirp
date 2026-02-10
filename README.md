# ⌁⌁ Chirp

[![PyPI version](https://img.shields.io/pypi/v/bengal-chirp.svg)](https://pypi.org/project/bengal-chirp/)
[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://pypi.org/project/bengal-chirp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Status: Alpha](https://img.shields.io/badge/status-alpha-orange.svg)](https://pypi.org/project/bengal-chirp/)

**A Python web framework for the modern web platform.**

```python
from chirp import App

app = App()

@app.route("/")
def index():
    return "Hello, World!"

app.run()
```

---

## Why Chirp?

Flask (2010) and FastAPI (2018) were designed for a different web. Flask assumes you render
full HTML pages or bolt on extensions for everything. FastAPI assumes you serve JSON to a
JavaScript frontend. Neither reflects where the web platform is in 2026:

- **Browser-native UI** — `<dialog>`, `popover`, View Transitions, container queries — most of what required a JS framework is now native HTML and CSS
- **HTML over the wire** — htmx proved that servers can send HTML fragments and the browser can swap them in — partial page updates with no custom JavaScript
- **Streaming HTML** — Send the page shell immediately and fill in content as data becomes available. No loading spinners, no skeleton screens
- **Server-Sent Events** — Push real-time updates over plain HTTP. No WebSocket protocol upgrade, no special infrastructure

Chirp is designed from scratch for this reality.

---

## Installation

```bash
pip install bengal-chirp
```

Requires Python 3.14+

---

## Quick Start

```bash
chirp new myapp && cd myapp && python app.py
```

| Function | Description |
|----------|-------------|
| `chirp new <name>` | Scaffold a new project |
| `chirp run <app>` | Start the dev server from an import string |
| `chirp check <app>` | Validate hypermedia contracts |
| `App()` | Create an application |
| `@app.route(path)` | Register a route handler |
| `Template(name, **ctx)` | Render a full template |
| `Template.inline(src, **ctx)` | Render from string (prototyping) |
| `Fragment(name, block, **ctx)` | Render a named template block |
| `Stream(name, **ctx)` | Stream HTML progressively |
| `EventStream(gen)` | Server-Sent Events stream |
| `app.run()` | Start the development server |

---

## Features

| Feature | Description | Docs |
|---------|-------------|------|
| **Routing** | Pattern matching, path params, method dispatch | [Routing →](https://lbliii.github.io/chirp/docs/routing/) |
| **Templates** | Kida integration, rendering, filters | [Templates →](https://lbliii.github.io/chirp/docs/templates/) |
| **Fragments** | Render named template blocks independently | [Fragments →](https://lbliii.github.io/chirp/docs/templates/fragments/) |
| **Streaming** | Progressive HTML rendering via Kida | [Streaming →](https://lbliii.github.io/chirp/docs/streaming/) |
| **SSE** | Server-Sent Events for real-time updates | [SSE →](https://lbliii.github.io/chirp/docs/streaming/server-sent-events/) |
| **Middleware** | CORS, sessions, static files, custom | [Middleware →](https://lbliii.github.io/chirp/docs/middleware/) |
| **Contracts** | Compile-time validation of hypermedia surface | [Reference →](https://lbliii.github.io/chirp/docs/reference/) |
| **Testing** | Test client, assertions, isolation utilities | [Testing →](https://lbliii.github.io/chirp/docs/testing/) |
| **Data** | Database integration and form validation | [Data →](https://lbliii.github.io/chirp/docs/data/) |

📚 **Full documentation**: [lbliii.github.io/chirp](https://lbliii.github.io/chirp/)

---

## Usage

<details>
<summary><strong>Return Values</strong> — Type-driven content negotiation</summary>

Route functions return *values*. The framework handles content negotiation based on the type:

```python
return "Hello"                                  # -> 200, text/html
return {"users": [...]}                         # -> 200, application/json
return Template("page.html", title="Home")      # -> 200, rendered via Kida
return Fragment("page.html", "results", items=x) # -> 200, rendered block
return Stream("dashboard.html", **async_ctx)    # -> 200, streamed HTML
return EventStream(generator())                 # -> SSE stream
return Response(body=b"...", status=201)         # -> explicit control
return Redirect("/login")                       # -> 302
```

No `make_response()`. No `jsonify()`. The type *is* the intent.

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

Built-in middleware: CORS, StaticFiles, HTMLInject, Sessions.

</details>

<details>
<summary><strong>Typed Contracts</strong> — Compile-time hypermedia validation</summary>

Chirp validates the server-client boundary at startup:

```python
issues = app.check()
for issue in issues:
    print(f"{issue.severity}: {issue.message}")
```

Every `hx-get`, `hx-post`, and `action` attribute in your templates is checked against the
registered route table. Every `Fragment` and `SSE` return type is checked against available
template blocks. Broken references become compile-time errors, not runtime 404s.

</details>

---

## Key Ideas

- **HTML over the wire.** Serve full pages, template fragments, streaming HTML, and
  Server-Sent Events. Built for htmx and the modern browser.
- **Kida built in.** Same author, no seam. Fragment rendering, streaming templates, and
  filter registration are first-class features, not afterthoughts.
- **Typed end-to-end.** Frozen config, frozen request, chainable response. Zero
  `type: ignore` comments.
- **Free-threading native.** Designed for Python 3.14t from the first line. Immutable data
  structures, ContextVar isolation.
- **Contracts, not conventions.** `app.check()` validates the full hypermedia surface at
  startup.
- **Minimal dependencies.** `kida` + `anyio`. Everything else is optional.

---

## Documentation

📚 **[lbliii.github.io/chirp](https://lbliii.github.io/chirp/)**

| Section | Description |
|---------|-------------|
| [Get Started](https://lbliii.github.io/chirp/docs/get-started/) | Installation and quickstart |
| [Core Concepts](https://lbliii.github.io/chirp/docs/core-concepts/) | App lifecycle, return values, configuration |
| [Routing](https://lbliii.github.io/chirp/docs/routing/) | Routes, requests, responses |
| [Templates](https://lbliii.github.io/chirp/docs/templates/) | Rendering, fragments, filters |
| [Streaming](https://lbliii.github.io/chirp/docs/streaming/) | HTML streaming and Server-Sent Events |
| [Middleware](https://lbliii.github.io/chirp/docs/middleware/) | Built-in and custom middleware |
| [Data](https://lbliii.github.io/chirp/docs/data/) | Database integration and forms |
| [Testing](https://lbliii.github.io/chirp/docs/testing/) | Test client and assertions |
| [Tutorials](https://lbliii.github.io/chirp/docs/tutorials/) | Flask migration, htmx patterns |
| [Reference](https://lbliii.github.io/chirp/docs/reference/) | API documentation |

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

A structured reactive stack — every layer written in pure Python for 3.14t free-threading.

| | | | |
|--:|---|---|---|
| **ᓚᘏᗢ** | [Bengal](https://github.com/lbliii/bengal) | Static site generator | [Docs](https://lbliii.github.io/bengal/) |
| **∿∿** | [Purr](https://github.com/lbliii/purr) | Content runtime | — |
| **⌁⌁** | **Chirp** | Web framework ← You are here | [Docs](https://lbliii.github.io/chirp/) |
| **=^..^=** | [Pounce](https://github.com/lbliii/pounce) | ASGI server | [Docs](https://lbliii.github.io/pounce/) |
| **)彡** | [Kida](https://github.com/lbliii/kida) | Template engine | [Docs](https://lbliii.github.io/kida/) |
| **ฅᨐฅ** | [Patitas](https://github.com/lbliii/patitas) | Markdown parser | [Docs](https://lbliii.github.io/patitas/) |
| **⌾⌾⌾** | [Rosettes](https://github.com/lbliii/rosettes) | Syntax highlighter | [Docs](https://lbliii.github.io/rosettes/) |

Python-native. Free-threading ready. No npm required.

---

## License

MIT
