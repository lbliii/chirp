# ⌁⌁ Chirp

[![PyPI version](https://img.shields.io/pypi/v/bengal-chirp.svg)](https://pypi.org/project/bengal-chirp/)
[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://pypi.org/project/bengal-chirp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Status: Alpha](https://img.shields.io/badge/status-alpha-orange.svg)](https://pypi.org/project/bengal-chirp/)

**A Python web framework for HTMX, HTML fragments, streaming HTML, and Server-Sent Events.**

Routes return intent — `Page`, `Fragment`, `EventStream`, `Suspense`, and friends — and Chirp
handles content negotiation, layout composition, and htmx awareness. Install as
**`bengal-chirp`**, import as **`chirp`**. Requires Python 3.14+.

Chirp ships routing, templates, forms, validation, sessions, auth, streaming HTML, SSE,
static files, security middleware, testing tools, and hypermedia contract checks in one
framework. JSON routes and explicit `Response` objects are supported when you need them.
Database access uses [Shapes](https://lbliii.github.io/chirp/docs/build-apps/forms-data/shapes/)
and an optional in-tree PostgreSQL driver. Background jobs, admin UIs, and email delivery
integrate at the seams — see [Non-goals](https://lbliii.github.io/chirp/docs/about/non-goals/).

Status: **alpha** (0.8.x). See [Public API](docs/public-api.md) for stable vs provisional exports.

📚 **Documentation:** [lbliii.github.io/chirp](https://lbliii.github.io/chirp/)

---

## Quick start

```bash
pip install 'bengal-chirp[ui]'   # [ui] optional but recommended for new projects
chirp new myapp && cd myapp
python app.py                      # http://127.0.0.1:8000
chirp check myapp:app              # validate hypermedia wiring
```

The scaffold includes routes, templates, and (with `[ui]`) ChirpUI layouts. No npm, no build step.

<details>
<summary><strong>Minimal example</strong> (no scaffold)</summary>

```python
from chirp import App

app = App()

@app.route("/")
def index():
    return "Hello, World!"

app.run()
```

For the smallest complete htmx loop (Page, Fragment, forms, tests), follow
[First Fragment App](https://lbliii.github.io/chirp/docs/get-started/first-fragment-app/).

</details>

---

## The core idea

One template, many access patterns. The return type expresses intent; Chirp negotiates the response:

```python
from chirp import App, Page, Request

app = App()

@app.route("/search")
async def search(request: Request):
    results = await db.search(request.query.get("q", ""))
    return Page("search.html", "results", results=results)
    # Browser navigation → full page. htmx request → just the "results" block.
```

No `make_response()`. No separate partials directory. The type *is* the intent.

Read [Philosophy](docs/philosophy.md) and [Return values](https://lbliii.github.io/chirp/docs/about/core-concepts/return-values/)
for the full model.

---

## Where to go next

| I want to… | Start here |
|------------|------------|
| Learn step by step | [Learning path](https://lbliii.github.io/chirp/docs/get-started/learning-path/) · [Get Started](https://lbliii.github.io/chirp/docs/get-started/) |
| Understand the architecture | [About](https://lbliii.github.io/chirp/docs/about/) · [Core concepts](https://lbliii.github.io/chirp/docs/about/core-concepts/) |
| Build features | [Build Apps](https://lbliii.github.io/chirp/docs/build-apps/) |
| Run runnable examples | [Examples index](examples/README.md) |
| Compare to other stacks | [When to use Chirp](https://lbliii.github.io/chirp/docs/about/comparison/) |
| See what's intentionally out of scope | [Non-goals](https://lbliii.github.io/chirp/docs/about/non-goals/) |
| Look up exports and stability | [Public API](docs/public-api.md) · [Reference](https://lbliii.github.io/chirp/docs/reference/) · [Glossary](https://lbliii.github.io/chirp/docs/reference/glossary/) |
| Contracts, tests, deployment | [Quality & Operations](https://lbliii.github.io/chirp/docs/quality/) |

---

## Learn Chirp (examples)

Follow the [learning path](https://lbliii.github.io/chirp/docs/get-started/learning-path/) on the docs site. Examples are tiered on purpose. **Do them in order.**

| Tier | Example | You will learn |
|------|---------|----------------|
| **1 — Basics** | [`standalone/hello`](examples/standalone/hello/), [`standalone/contacts`](examples/standalone/contacts/) | Routes, forms, `Page` / `Fragment`, validation |
| **2 — App shell** | [`chirpui/contacts_shell`](examples/chirpui/contacts_shell/) | ChirpUI shell, `_actions.py`, `_context.py`, boosted nav |
| **3 — Capstone** | [`chirpui/lucky_cat`](examples/chirpui/lucky_cat/) | Signals, Suspense, SSE, OOB, secure stack |

<details>
<summary><strong>Capstone demo — Lucky Cat</strong> (tier 3, not the on-ramp)</summary>

**Live:** [luckycat-production.up.railway.app](https://luckycat-production.up.railway.app) ·
**Source:** [`examples/chirpui/lucky_cat/`](examples/chirpui/lucky_cat/)

A simulated trading-floor UI built on server-owned signals, SSE, Suspense, and OOB swaps — no
client framework. Complete tiers 1–2 first.

</details>

Most day-to-day apps use a small set: `App`, `@app.route`, `Template`, `Page`, forms,
`ValidationError`, and `chirp check`. Streaming, signals, and filesystem routing are the next
layer — the tiered examples introduce them in order.

---

## Installation

```bash
# pip
pip install bengal-chirp

# uv
uv add bengal-chirp
```

<details>
<summary><strong>Optional extras</strong></summary>

| Extra | Adds |
|-------|------|
| `[ui]` | [chirp-ui](https://github.com/lbliii/chirp-ui) components and themes (`chirp new` emits ChirpUI layouts) |
| `[forms]` | Multipart form parsing |
| `[sessions]` | Signed cookie sessions |
| `[auth]` | Argon2 password hashing |
| `[passkeys]` | WebAuthn / passkeys |
| `[ai]` | LLM streaming (`httpx`) |
| `[data-pg]` | PostgreSQL via in-tree driver (no extra deps) |
| `[testing]` | `httpx` test client transport |
| `[redis]` | Redis-backed sessions and rate limiting |
| `[markdown]` | Patitas + Rosettes markdown rendering |
| `[config]` | `python-dotenv` for `.env` loading |
| `[all]` / `[full]` | Common optional features bundled |

```bash
pip install 'bengal-chirp[ui]'
# or: uv add 'bengal-chirp[ui]'
```

When chirp-ui is installed, `chirp check` verifies that `chirpui-*` classes resolve to backing styles.

</details>

---

## Reference

<details>
<summary><strong>CLI</strong></summary>

| Command | Description |
|---------|-------------|
| `chirp new <name>` | Scaffold an auth-ready project |
| `chirp new <name> --shell` | Scaffold with a persistent app shell (topbar + sidebar) |
| `chirp new <name> --stream` | Simulated token streaming (`TemplateStream` + `EventStream`) |
| `chirp new <name> --sse` | Scaffold with SSE boilerplate (`EventStream`, `sse_scope`) |
| `chirp new <name> --ai` | Scaffold AI chat with tools, SSE activity feed, and secure stack |
| `chirp run <app>` | Start the dev server from an import string |
| `chirp dev <app>` | Dev server with Chirp DevTools |
| `chirp check <app>` | Validate hypermedia contracts |
| `chirp check <app> --warnings-as-errors` | Fail CI on contract warnings |
| `chirp check <app> --coverage` | Show contract coverage counters |
| `chirp check <app> --deploy` | Deploy preflight (implies `--warnings-as-errors`) |
| `chirp routes <app>` | Print the registered route table |
| `chirp --version` | Print chirp, kida, pounce, and Python versions |

</details>

<details>
<summary><strong>Return types</strong> — type-driven content negotiation</summary>

```python
return "Hello"                                   # -> 200, text/html
return {"users": [...]}                          # -> 200, application/json
return Template("page.html", title="Home")        # -> 200, rendered via Kida
return Page("search.html", "results", items=x)   # -> Fragment or Template (auto)
return Fragment("page.html", "results", items=x) # -> 200, rendered block
return Stream("dashboard.html", **async_ctx)     # -> 200, streamed HTML
return Suspense("dashboard.html", stats=...)     # -> shell + OOB swaps
return EventStream(generator())                  # -> SSE stream
return hx_redirect("/dashboard")                 # -> Location + HX-Redirect
return Response(body=b"...", status=201)          # -> explicit control
return Redirect("/login")                        # -> 302
```

For htmx-driven form posts that should trigger full-page navigation, prefer `hx_redirect()`
so both plain browser and htmx requests follow the redirect correctly.

</details>

<details>
<summary><strong>Experimental HTTP QUERY</strong> — safe body-bearing searches</summary>

Chirp supports RFC 10008 `QUERY` on explicit ASGI routes for controlled
early-adopter use. Choose it only when a read-only query is too large or
structured for a practical URI; ordinary bookmarkable searches and native HTML
forms should stay GET.

The route declares accepted request media types, while the handler keeps using
Chirp's normal typed HTML returns and one-template/named-block render surface.
Browser, Pounce, Uvicorn, and Nginx proof exists, but stable promotion and
universal proxy/CDN support are **not** claimed. Keep a GET fallback and verify
the exact deployment path.

See the [HTTP QUERY adoption guide](https://lbliii.github.io/chirp/docs/build-apps/pages-navigation/http-query/)
for request failures, CORS, redirects, conditional responses, explicit cache
opt-in, compatibility evidence, and the remaining release gates.

</details>

<details>
<summary><strong>Stream vs Suspense vs EventStream</strong></summary>

Picking the wrong one is the most common return-type mistake:

| Type | Shell first? | Transport | Use for | Not for |
|------|--------------|-----------|---------|---------|
| `Stream` | No — flush blocks as they complete | Single chunked HTTP response | Slow first-byte pages with independent sections | Post-load updates |
| `Suspense` | Yes — shell renders, deferred blocks stream as OOB swaps | Single chunked HTTP response | Dashboards with multiple slow data sources, one round trip | Post-load updates |
| `EventStream` | N/A — pure event channel | SSE (`text/event-stream`, long-lived) | Notifications, tickers, chat tails *after* the page loads | Initial page render |

**Rule of thumb:** initial render that streams → `Suspense` (or `Stream` for SEO-heavy sections);
updates after the page loads → `EventStream` for page-local regions, `signal()` for cross-page
chrome. Multi-target mutations → `OOB` / `FormAction`.

See the [realtime decision tree](https://lbliii.github.io/chirp/docs/build-apps/streaming-updates/realtime-decision-tree/).

</details>

<details>
<summary><strong>Fragments and htmx</strong></summary>

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

</details>

<details>
<summary><strong>Forms and validation</strong></summary>

```python
from chirp import Page, ValidationError
from chirp.validation import validate, required, email, max_length

@app.route("/contacts", methods=["POST"])
async def create_contact(request: Request):
    form = await request.form()
    result = validate(form, {
        "name":  [required, max_length(200)],
        "email": [required, email],
    })
    if not result:
        return ValidationError("contacts.html", "form", errors=result.errors, form=form)
    contacts.append(Contact(**result.data))
    return Page("contacts.html", "list", contacts=contacts)
```

`ValidationError` returns 422 with the re-rendered form fragment for htmx; non-htmx requests get
the full page back.

</details>

<details>
<summary><strong>Server-Sent Events</strong></summary>

```python
@app.route("/notifications")
async def notifications(request: Request):
    async def stream():
        async for event in notification_bus.subscribe(request.user):
            yield Fragment("components/notification.html", event=event)
    return EventStream(stream())
```

Combined with htmx's SSE support, the server renders HTML and the browser swaps it in.
The managed htmx 4 preview uses native `hx-sse:connect`: rendered `Fragment`
updates are unnamed HTML frames, and `Fragment(target="feed")` becomes an
unnamed `<hx-partial hx-target="#feed">` update. Named `SSEEvent`s remain DOM
events. Htmx 2 keeps its existing `sse-connect` / `sse-swap` channels.

</details>

<details>
<summary><strong>Middleware</strong></summary>

No base class. No inheritance. A middleware is anything that matches the protocol:

```python
async def timing(request: Request, next: Next) -> Response:
    start = time.monotonic()
    response = await next(request)
    elapsed = time.monotonic() - start
    return response.with_header("X-Time", f"{elapsed:.3f}")

app.add_middleware(timing)
```

Built-in middleware: CORS, StaticFiles, HTMLInject, Sessions, SecurityHeaders, CSRF, Auth, and more.
See [Request pipeline](https://lbliii.github.io/chirp/docs/build-apps/request-pipeline/).

</details>

<details>
<summary><strong>Contracts</strong> — static hypermedia validation</summary>

```python
app.check()                        # report and exit non-zero on errors
app.check(warnings_as_errors=True) # strict mode
```

Every `hx-get`, `hx-post`, and `action` attribute in templates is checked against the route table.
Every `Fragment` and SSE return type is checked against available template blocks.

```bash
chirp check myapp:app --warnings-as-errors
```

See [Contracts](https://lbliii.github.io/chirp/docs/quality/contracts-debugging/).

</details>

<details>
<summary><strong>DevTools</strong></summary>

```bash
chirp dev myapp:app
```

Open the app in a browser and press `Ctrl+Shift+D` for Chirp DevTools — htmx activity, effective
`hx-*` inheritance, render plans, EventStream traces, View Transitions, and Swap Doctor warnings.

```javascript
window.ChirpHtmxDebug.help()
window.ChirpHtmxDebug.exportRecordsJson()
```

</details>

<details>
<summary><strong>Features index</strong></summary>

| Topic | Docs |
|-------|------|
| HTMX patterns | [htmx Patterns](https://lbliii.github.io/chirp/docs/tutorials/htmx-patterns/) |
| Routing & filesystem layout | [Pages & navigation](https://lbliii.github.io/chirp/docs/build-apps/pages-navigation/) |
| Templates & fragments | [HTML fragments](https://lbliii.github.io/chirp/docs/build-apps/html-fragments/) |
| Forms & data | [Forms & validation](https://lbliii.github.io/chirp/docs/build-apps/forms-data/) |
| Streaming & SSE | [Streaming updates](https://lbliii.github.io/chirp/docs/build-apps/streaming-updates/) |
| Middleware | [Request pipeline](https://lbliii.github.io/chirp/docs/build-apps/request-pipeline/) |
| Contracts & debugging | [Quality](https://lbliii.github.io/chirp/docs/quality/) |
| Testing | [Testing](https://lbliii.github.io/chirp/docs/quality/testing/) |
| Optional UI layer | [chirp-ui](https://github.com/lbliii/chirp-ui) |

</details>

---

## Production

Chirp apps run on **[Pounce](https://github.com/lbliii/pounce)**, a production-grade ASGI server with
HTTP/2, graceful shutdown, Prometheus metrics, rate limiting, and multi-worker scaling.

```bash
chirp check myapp:app --warnings-as-errors   # hypermedia contracts
pounce check --app myapp:app                 # server preflight
```

See the [deployment guide](https://lbliii.github.io/chirp/docs/quality/deployment/production/).

<details>
<summary><strong>Benchmarks</strong></summary>

Synthetic benchmarks comparing Chirp, FastHTML, FastAPI, Flask, Starlette, and Litestar:

```bash
uv sync --extra benchmark
uv run poe benchmark
```

See the [committed baseline and full artifact](benchmarks/README.md#committed-network-baseline)
for current results, caveats, environment metadata, and runners.

</details>

---

## Development

```bash
git clone https://github.com/lbliii/chirp.git
cd chirp
make install          # once per worktree (.python-version → 3.14t, docs deps)
make test
make site-serve     # docs site at http://127.0.0.1:5173
```

New Conductor worktree? Same flow: **`make install`** then **`make site-serve`**
(or `cd site && ./bengal s`). Python pin and free-threading env live in git
(`.python-version`, `config/python.env`, `site/bengal`); only `.venv` is recreated.

Run commands from the repository root. If an ancestor directory has old multi-repo dependency
overrides, clone Chirp outside that parent before running `make install`.

Docs-site details: `site/AGENTS.md`.

---

## The Bengal Ecosystem

Python-native stack for 3.14t free-threading. Chirp is the web framework; packages like
`chirp-ui` sit on top as optional companions.

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
| **⚡** | [Zoomies](https://github.com/lbliii/zoomies) | QUIC / HTTP/3 | — |

---

## License

MIT
