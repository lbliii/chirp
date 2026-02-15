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

## What is Chirp?

Chirp is a Python web framework built for the modern web platform: browser-native UI, HTML over the wire, streaming responses, and Server-Sent Events. Return values drive content negotiation — no `make_response()`, no `jsonify()`. The type *is* the intent.

**What's good about it:**

- **Browser-native UI** — `<dialog>`, `popover`, View Transitions, container queries. Most of what required a JS framework is now native HTML and CSS.
- **HTML over the wire** — Serve full pages, template fragments, streaming HTML, and SSE. Built for htmx and the modern browser.
- **Streaming HTML** — Send the page shell immediately and fill in content as data becomes available. No loading spinners, no skeleton screens.
- **Server-Sent Events** — Push real-time updates over plain HTTP. No WebSocket protocol upgrade, no special infrastructure.

---

## Installation

```bash
# pip
pip install bengal-chirp

# uv
uv add bengal-chirp
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
| `Page(name, block, **ctx)` | Auto Fragment or Template based on request |
| `Fragment(name, block, **ctx)` | Render a named template block |
| `Stream(name, **ctx)` | Stream HTML progressively |
| `Suspense(name, **ctx)` | Shell first, OOB swaps for deferred data |
| `EventStream(gen)` | Server-Sent Events stream |
| `app.run()` | Start the development server |

---

## Features

| Feature | Description | Docs |
|---------|-------------|------|
| **Routing** | Pattern matching, path params, method dispatch | [Routing →](https://lbliii.github.io/chirp/docs/routing/) |
| **Filesystem routing** | Route discovery from `pages/` with layouts | [Filesystem →](https://lbliii.github.io/chirp/docs/routing/filesystem-routing/) |
| **Templates** | Kida integration, rendering, filters | [Templates →](https://lbliii.github.io/chirp/docs/templates/) |
| **Fragments** | Render named template blocks independently | [Fragments →](https://lbliii.github.io/chirp/docs/templates/fragments/) |
| **Forms** | `form_or_errors`, form macros, validation | [Forms →](https://lbliii.github.io/chirp/docs/data/forms-validation/) |
| **Streaming** | Progressive HTML rendering via Kida | [Streaming →](https://lbliii.github.io/chirp/docs/streaming/) |
| **SSE** | Server-Sent Events for real-time updates | [SSE →](https://lbliii.github.io/chirp/docs/streaming/server-sent-events/) |
| **Middleware** | CORS, sessions, static files, security headers, custom | [Middleware →](https://lbliii.github.io/chirp/docs/middleware/) |
| **Contracts** | Compile-time validation of hypermedia surface | [Reference →](https://lbliii.github.io/chirp/docs/reference/) |
| **Testing** | Test client, assertions, isolation utilities | [Testing →](https://lbliii.github.io/chirp/docs/testing/) |
| **Data** | Database integration and form validation | [Data →](https://lbliii.github.io/chirp/docs/data/) |

📚 **Full documentation**: [lbliii.github.io/chirp](https://lbliii.github.io/chirp/)

---

## Production Deployment

Chirp apps run on **[pounce](https://github.com/lbliii/pounce)**, a production-grade ASGI server with enterprise features built-in:

### Automatic Features (Zero Configuration)
- ✅ **WebSocket compression** — 60% bandwidth reduction
- ✅ **HTTP/2 support** — Multiplexed streams, server push
- ✅ **Graceful shutdown** — Finishes active requests on SIGTERM
- ✅ **Zero-downtime reload** — `kill -SIGUSR1` for hot code updates
- ✅ **Built-in health endpoint** — `/health` for Kubernetes probes

### Production Features (Configurable)
- 📊 **Prometheus metrics** — `/metrics` endpoint for monitoring
- 🛡️ **Per-IP rate limiting** — Token bucket algorithm, configurable burst
- 📦 **Request queueing** — Load shedding during traffic spikes
- 🐛 **Sentry integration** — Automatic error tracking and reporting
- 🔄 **Multi-worker mode** — CPU-based auto-scaling

### Quick Start: Production Mode

```python
from chirp import App, AppConfig

# Production configuration
config = AppConfig(
    debug=False,  # ← Enables production mode
    workers=4,
    metrics_enabled=True,
    rate_limit_enabled=True,
    sentry_dsn="https://...",
)

app = App(config=config)

@app.route("/")
def index():
    return "Hello, Production!"

app.run()  # ← Automatically uses production server
```

### CLI Production Mode

```bash
# Development (single worker, auto-reload)
chirp run myapp:app

# Production (multi-worker, all features)
chirp run myapp:app --production --workers 4 --metrics --rate-limit
```

### Docker Deployment

```dockerfile
FROM python:3.14-slim
WORKDIR /app
COPY . .
RUN pip install bengal-chirp
CMD ["chirp", "run", "myapp:app", "--production", "--workers", "4"]
```

📦 **Full deployment guide**: [docs/deployment/production.md](docs/deployment/production.md)

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

Built-in middleware: CORS, StaticFiles, HTMLInject, Sessions, SecurityHeaders.

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
- **Minimal dependencies.** `kida-templates` + `anyio` + `bengal-pounce`. Everything else is optional.

---

## Documentation

📚 **[lbliii.github.io/chirp](https://lbliii.github.io/chirp/)**

| Section | Description |
|---------|-------------|
| [Get Started](https://lbliii.github.io/chirp/docs/get-started/) | Installation and quickstart |
| [Core Concepts](https://lbliii.github.io/chirp/docs/core-concepts/) | App lifecycle, return values, configuration |
| [Routing](https://lbliii.github.io/chirp/docs/routing/) | Routes, filesystem routing, requests |
| [Templates](https://lbliii.github.io/chirp/docs/templates/) | Rendering, fragments, filters |
| [Streaming](https://lbliii.github.io/chirp/docs/streaming/) | HTML streaming and Server-Sent Events |
| [Middleware](https://lbliii.github.io/chirp/docs/middleware/) | Built-in and custom middleware |
| [Data](https://lbliii.github.io/chirp/docs/data/) | Database integration and forms |
| [Testing](https://lbliii.github.io/chirp/docs/testing/) | Test client and assertions |
| [Deployment](https://lbliii.github.io/chirp/docs/deployment/) | Production deployment with Pounce |
| [Tutorials](https://lbliii.github.io/chirp/docs/tutorials/) | Flask migration, htmx patterns |
| [Examples](https://lbliii.github.io/chirp/docs/examples/) | RAG demo, production stack, API |
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
