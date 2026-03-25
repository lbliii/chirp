# Philosophy: Hypermedia-Native Python

Chirp is built on one idea: **the server renders HTML, the browser renders UI, and the return type connects them.**

This isn't a new architecture. It's what the web always was — before single-page applications convinced us we needed a JavaScript runtime between the server and the user. Chirp brings it back with modern tools: streaming HTML, Server-Sent Events, htmx fragment swaps, and Python's free-threading.

We call this approach **hypermedia-native** because the application speaks hypermedia at every layer — not JSON that gets translated into HTML on the client, but HTML from the start.

---

## The Five Opinions

### 1. The return type is the architecture

Most frameworks make you construct response objects. Chirp lets you return *intent*:

```python
return Page("search.html", "results", items=items)
```

That single line does different things depending on context:
- Browser navigation → renders the full page with layouts
- htmx request → renders just the `results` block
- htmx request targeting a specific layout region → renders from that depth

The framework negotiates. The developer declares.

This extends to every interaction pattern:

| Return type | Intent |
|---|---|
| `Template` | Render a full page |
| `Fragment` | Render a single block |
| `Page` | Let the framework decide (fragment or full page) |
| `OOB` | Update multiple DOM targets in one response |
| `EventStream` | Push real-time updates via SSE |
| `Suspense` | Send the shell immediately, stream deferred blocks |
| `ValidationError` | Re-render a form with errors (422) |
| `FormAction` | Fragments for htmx, redirect for plain browsers |

No `make_response()`. No content-type negotiation code. No separate API layer. The type *is* the intent.

### 2. One template, many access patterns

A chirp template is not a view layer — it's the *interface definition* for a piece of UI. A single template with named blocks serves as:

- **A full page** when the browser navigates directly
- **A fragment** when htmx swaps a block
- **An SSE payload** when an EventStream yields a Fragment
- **A deferred block** when Suspense resolves an awaitable

```html
{% block results %}
<div id="results">
  {% for item in items %}
    <div class="result">{{ item.title }}</div>
  {% endfor %}
</div>
{% endblock %}
```

That block is addressable from four different code paths — a route handler, an OOB swap, an SSE generator, and a Suspense resolver — using the same template, same context shape, same HTML. No partials directory. No separate component format. No serialization boundary.

### 3. Contracts, not conventions

Rails popularized "convention over configuration." Chirp takes a different position: **verification over convention.**

```bash
chirp check myapp:app
```

At startup (or in CI), chirp validates the full hypermedia surface:

- Every `hx-get`, `hx-post`, `action` attribute in templates → does the route exist?
- Every `Fragment` return → does the block exist in that template?
- Every `sse-connect` / `sse-swap` → is the SSE structure valid?
- Every `target` → does the element ID exist?

Convention tells you where to put files. Contracts tell you when the system is broken. Chirp chooses the one that catches bugs.

### 4. SSE over WebSockets, always

Server-Sent Events are HTTP. They work through proxies, load balancers, CDNs. They reconnect automatically. They need no protocol upgrade, no special infrastructure, no client library.

WebSockets are bidirectional — but most "real-time" features are server-push: notifications, live scores, dashboard updates, streaming LLM responses. SSE handles all of these with less code and fewer failure modes.

Chirp makes SSE a first-class return type:

```python
@app.route("/feed")
def feed():
    async def generate():
        async for event in bus.subscribe():
            yield Fragment("dashboard.html", "metric", data=event)
    return EventStream(generate())
```

The framework handles heartbeats, disconnect detection, error boundaries per event, and automatic cleanup. Your generator yields values; chirp handles the protocol.

### 5. The browser is the framework

`<dialog>` replaced modal libraries. `popover` replaced dropdown libraries. View Transitions replaced page transition libraries. Container queries replaced responsive JavaScript. `:has()` replaced parent selectors. `<details>` replaced accordion libraries.

Most of what React component libraries provide is now native HTML and CSS. Chirp leans into this — the framework's job is to get the right HTML to the browser, not to replace the browser.

When client-side behavior is needed, chirp supports Alpine.js for local state and Islands for isolated interactive widgets. But the default is: **if the browser can do it, let the browser do it.**

---

## What Chirp Is Not

- **Not a REST API framework.** If your primary output is JSON for a separate frontend, use FastAPI. Chirp's strength is rendering HTML.
- **Not a Django replacement.** Chirp doesn't include an ORM, admin panel, or auth backend. It's smaller and sharper — a framework for the rendering layer, not the entire stack.
- **Not a static site generator.** Chirp serves dynamic HTML. For static sites in the Bengal ecosystem, see [Bengal](https://github.com/lbliii/bengal).
- **Not opinionated about your database.** Use SQLAlchemy, SQLModel, raw SQL, or no database at all. Chirp renders HTML — where the data comes from is your choice.

---

## The Stack

A hypermedia-native chirp application uses:

| Layer | Tool | Role |
|---|---|---|
| Server | **Pounce** | ASGI server, free-threading, multi-worker |
| Framework | **Chirp** | Routing, middleware, content negotiation |
| Templates | **Kida** | HTML rendering, fragment blocks, streaming |
| Interactivity | **htmx** | Fragment swaps, SSE, form handling |
| Real-time | **SSE** | Server-push via EventStream |
| Local state | **Alpine.js** | When needed — toggles, drag-drop, client validation |
| Styling | **CSS** | Your design system, or chirp-ui as a companion |

No build step. No node_modules. No client-side routing. No state management library. No GraphQL. No REST serialization layer.

Python renders HTML. The browser renders UI. htmx connects them.
