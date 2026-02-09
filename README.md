# ⌁⌁ chirp

A Python web framework for the modern web platform.

```python
from chirp import App

app = App()

@app.route("/")
def index():
    return "Hello, World!"

app.run()
```

Chirp serves HTML beautifully — full pages, fragments, streams, and real-time events — all
through its built-in template engine, [kida](https://github.com/lbliii/kida).

**Status:** Alpha — Phases 0-7 complete, plus typed hypermedia contracts. Routing, Kida
integration, fragment rendering, middleware, streaming HTML, Server-Sent Events, test
utilities, and compile-time validation of the server-client surface all implemented. 53
source modules. See [ROADMAP.md](ROADMAP.md) for the full vision.

---

## Why Chirp?

Flask (2010) and FastAPI (2018) were designed for a different web. Flask assumes you render
full HTML pages or bolt on extensions for everything. FastAPI assumes you serve JSON to a
JavaScript frontend. Neither reflects where the web platform is in 2026:

- The browser has `<dialog>`, `popover`, View Transitions, container queries, and anchor
  positioning. Most of what required a JS framework is now native HTML and CSS.
- htmx proved that servers can send HTML fragments and the browser can swap them in —
  partial page updates with no custom JavaScript.
- Streaming HTML lets the server send the page shell immediately and fill in content as
  data becomes available. No loading spinners, no skeleton screens.
- Server-Sent Events push real-time updates over plain HTTP. No WebSocket protocol upgrade,
  no special infrastructure.

No Python framework is built around these capabilities. Flask and Django treat templates as
"render a full page, return a string." FastAPI doesn't have a template story at all. None of
them can render a template *block* as a fragment. None of them stream HTML as it renders.
None of them have first-class SSE support for pushing HTML updates.

Chirp is designed from scratch for this reality.

---

## Quick Start

```python
from chirp import App

app = App()

@app.route("/")
def index():
    return "Hello, World!"

app.run()
```

Five lines to hello world. Flask-familiar on the surface — because Flask got the surface
right.

---

## Return Values, Not Response Construction

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

---

## Fragments and htmx

This is Chirp's key innovation. Kida can render a named block from a template independently,
without rendering the whole page:

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

---

## Streaming and Real-Time

**Streaming HTML** — Kida renders template sections as they complete. The browser receives
the shell immediately and content fills in progressively:

```python
@app.route("/dashboard")
async def dashboard(request: Request):
    return Stream("dashboard.html",
        header=site_header(),
        stats=await load_stats(),
        activity=await load_activity(),
    )
```

**Server-Sent Events** — push Kida-rendered HTML fragments to the browser in real-time:

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

---

## Middleware

No base class. No inheritance. A middleware is anything that matches the protocol:

```python
async def timing(request: Request, next: Next) -> Response:
    start = time.monotonic()
    response = await next(request)
    elapsed = time.monotonic() - start
    return response.with_header("X-Time", f"{elapsed:.3f}")

app.add_middleware(timing)
```

A function that takes a request and a `next`, returns a response. Built-in middleware:

- **CORS** — cross-origin resource sharing
- **StaticFiles** — static file serving with index resolution, trailing-slash redirects, custom 404 pages, and root-prefix support (`prefix="/"` for static site hosting)
- **HTMLInject** — inject a snippet (e.g. a live-reload script) into every HTML response before `</body>`
- **Sessions** — signed cookie sessions

---

## Typed Hypermedia Contracts

Chirp validates the server-client boundary at startup — something React/Next.js can't do
without JavaScript:

```python
issues = app.check()
for issue in issues:
    print(f"{issue.severity}: {issue.message}")
```

Every `hx-get`, `hx-post`, and `action` attribute in your templates is checked against the
registered route table. Every `Fragment` and `SSE` return type is checked against available
template blocks. Broken references become compile-time errors, not runtime 404s.

Use the `@contract` decorator for fine-grained route-level contracts:

```python
from chirp.contracts import contract, FragmentContract

@app.route("/search")
@contract(
    returns=[FragmentContract("search.html", "results_list")],
    htmx_triggers=["hx-get"],
)
async def search(request: Request):
    ...
```

---

## Key Ideas

- **HTML over the wire.** Serve full pages, template fragments, streaming HTML, and
  Server-Sent Events. Built for htmx and the modern browser.
- **Kida built in.** Same author, no seam. Fragment rendering, streaming templates, and
  filter registration are first-class features, not afterthoughts.
- **Typed end-to-end.** Frozen config, frozen request, chainable response. Zero
  `type: ignore` comments. `ty` passes clean.
- **Free-threading native.** Designed for Python 3.14t from the first line. Immutable data
  structures, ContextVar isolation, `_Py_mod_gil = 0`.
- **Contracts, not conventions.** `app.check()` validates the full hypermedia surface at
  startup — every `hx-get` resolves to a route, every `Fragment` references a real block.
  Compile-time safety for the server-client boundary.
- **Minimal dependencies.** `kida` + `anyio`. Everything else is optional.

---

## Requirements

- Python >= 3.14

---

## Part of the Bengal Ecosystem

```
purr        Content runtime   (connects everything)
pounce      ASGI server       (serves apps)
chirp       Web framework     (serves HTML)
kida        Template engine   (renders HTML)
patitas     Markdown parser   (parses content)
rosettes    Syntax highlighter (highlights code)
bengal      Static site gen   (builds sites)
```

---

## License

MIT
