# ⌁⌁ Chirp

[![PyPI version](https://img.shields.io/pypi/v/bengal-chirp.svg)](https://pypi.org/project/bengal-chirp/)
[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://pypi.org/project/bengal-chirp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Status: Alpha](https://img.shields.io/badge/status-alpha-orange.svg)](https://pypi.org/project/bengal-chirp/)

![An active weaverbird weaving named template blocks through browser, fragment, stream, and event paths in a screen-printed jungle workshop.](site/assets/images/chirp-hypermedia-weaver-hero.webp)

**One template. Every interaction. Checked before deploy.**

Chirp is the hypermedia-native Python framework for server-rendered product UIs.
Routes return typed template responses. Chirp reuses one template's named blocks
for pages, htmx fragments, streaming HTML, and live SSE updates. `chirp check`
catches broken routes, blocks, and targets before users find them.

Build the app on the server without maintaining a parallel SPA, a second set of
partials, or a JavaScript build pipeline. Install as **`bengal-chirp`**, import as
**`chirp`**. Python 3.14+ required.

## Why Chirp

Server-rendered applications often split a single interaction across page templates,
fragment templates, browser conventions, and test-only assumptions. That makes a
small UI change hard to reason about: which template owns the state, which route
returns it, and which browser target receives it?

Chirp keeps those declarations together. A route's return type says what the
interaction needs; named blocks give that response a precise render target; the
compiler checks the wiring. The result is a live ASGI app that stays legible as it
gains forms, streaming, and realtime updates.

## Quick start

```bash
pip install 'bengal-chirp[ui]'
chirp new myapp && cd myapp
python app.py                      # http://127.0.0.1:8000
chirp check myapp:app              # validate hypermedia wiring
```

`[ui]` is optional, but recommended for new projects: `chirp new` emits
[chirp-ui](https://github.com/lbliii/chirp-ui) layouts. No npm or build step.
For the smallest complete htmx loop, follow
[First Fragment App](https://lbliii.github.io/chirp/docs/get-started/first-fragment-app/).

## The core model

```python
from chirp import App, Page, Request

app = App()

@app.route("/search")
async def search(request: Request):
    results = await db.search(request.query.get("q", ""))
    return Page("search.html", "results", results=results)
    # Navigation renders the page; htmx gets the named "results" block.
```

`Page` names the template and block. Chirp uses the same return model for pages,
fragments, streams, and events. See the full
[return-value reference](https://lbliii.github.io/chirp/docs/about/core-concepts/return-values/)
for every render surface.

Run `chirp check` in development and CI. It diagnoses missing routes, template
blocks, fragment targets, and incompatible hypermedia declarations. Runtime
transition traces and tests use the same compiled model. The primary output is a
live ASGI application; `chirp freeze` is an optional static projection for
compatible routes.

Read the [hypermedia compiler architecture](docs/hypermedia-application-compiler.md)
for the foundation, and the tested
[Full-Application Journey](https://lbliii.github.io/chirp/docs/tutorials/full-application-journey/)
for database, mutation, validation, boosted navigation, SSE, diagnostics, and
optional-export proof.

## What you can build

Chirp includes routing, templates, forms, validation, sessions, auth helpers,
streaming HTML, SSE, static files, security middleware, and testing tools.
Shapes provides database access, with an optional in-tree PostgreSQL driver.

Use it for server-owned product UIs: dashboards, back-office workflows, customer
portals, collaborative tools, and apps where HTML is the useful unit of work.
JSON routes and explicit `Response` objects remain available when that is the
right boundary. Background jobs, admin UIs, and email delivery integrate at the
seams; see [Non-goals](https://lbliii.github.io/chirp/docs/about/non-goals/).

The framework's useful constraints are deliberate:

| Need | Chirp approach |
| --- | --- |
| A full page and a small update | One template with named blocks |
| Slow initial sections | `Stream` or `Suspense` |
| Updates after load | `EventStream` or signals |
| Form errors | Typed validation result re-renders the relevant block |
| Confidence before deploy | `chirp check --warnings-as-errors` |

## Explore

| I want to… | Start here |
| --- | --- |
| Learn the model | [Learning path](https://lbliii.github.io/chirp/docs/get-started/learning-path/) · [Get Started](https://lbliii.github.io/chirp/docs/get-started/) |
| Build features | [Build Apps](https://lbliii.github.io/chirp/docs/build-apps/) |
| Understand returns and blocks | [Core concepts](https://lbliii.github.io/chirp/docs/about/core-concepts/) |
| Debug contracts and deploy | [Quality & Operations](https://lbliii.github.io/chirp/docs/quality/) |
| Run examples | [Examples index](examples/README.md) |
| Compare stacks or check scope | [When to use Chirp](https://lbliii.github.io/chirp/docs/about/comparison/) · [Non-goals](https://lbliii.github.io/chirp/docs/about/non-goals/) |

Start with the tiered examples in order: basics, an app shell, then the capstone.
Most applications need `App`, `@app.route`, `Template`, `Page`, forms,
`ValidationError`, and `chirp check` before they need signals or streaming.

## Everyday tools

The `chirp` command can scaffold, run, inspect, and validate an application.
`chirp new <name> --shell` starts with a persistent app shell; `--stream`,
`--sse`, `--ai`, and `--skill` add focused examples of those patterns. `chirp
dev <app>`
starts the development server with Chirp DevTools; `chirp routes <app>` prints
the route table; `chirp check <app> --coverage` shows contract coverage.

The core package stays small. Add only the extras you use: `[forms]` for
multipart parsing, `[sessions]`, `[auth]`, and `[passkeys]` for identity work,
`[skill]` for signed skill envelopes (`cryptography`), `[ai]` for LLM
streaming, `[data-pg]` for PostgreSQL, `[testing]` for an `httpx` transport,
`[redis]` for Redis-backed sessions and rate limiting, or `[markdown]` for
Patitas and Rosettes. When chirp-ui is installed, `chirp check` also verifies
that `chirpui-*` classes resolve to backing styles.

## Production and deployment

Chirp apps run on [Pounce](https://github.com/lbliii/pounce), an ASGI server with
HTTP/2, graceful shutdown, Prometheus metrics, rate limiting, and multi-worker
scaling. Validate both layers before deployment:

```bash
chirp check myapp:app --warnings-as-errors
pounce check --app myapp:app
```

Follow the [production deployment guide](https://lbliii.github.io/chirp/docs/quality/deployment/production/)
for deployment posture and caveats. Framework-owned paths have free-threading
coverage under Python 3.14t; application globals and optional integrations need
their own synchronization proof.

Synthetic comparisons are available in the [committed baseline](benchmarks/README.md#committed-network-baseline).
They describe only the captured environment. They do not promise production
capacity or universal performance. The machine-checked
[claims ledger](docs/design/public-claims.json) governs public positioning.

### Experimental HTTP QUERY

Chirp supports RFC 10008 `QUERY` on explicit ASGI routes for controlled
early-adopter use. Use it only when a read-only query is too large or structured
for a practical URI; bookmarkable searches and native HTML forms should stay GET.
The route declares accepted media types while the handler keeps Chirp's normal
typed HTML returns and one-template/named-block render surface.
Keep a GET fallback and verify the exact deployment path. Browser, Pounce,
Uvicorn, and Nginx proof exists, but stable promotion and universal proxy/CDN support are **not** claimed.

See the [HTTP QUERY adoption guide](https://lbliii.github.io/chirp/docs/build-apps/pages-navigation/http-query/)
for compatibility evidence and release gates.

## Railway templates

Deploy a ready-to-run example on Railway: [Forum](https://railway.com/deploy/chirp-forum?referralCode=KU30ob&utm_medium=integration&utm_source=template&utm_campaign=generic),
[Feedback Board](https://railway.com/deploy/chirp-feedback-board?referralCode=KU30ob&utm_medium=integration&utm_source=template&utm_campaign=generic),
[Changelog](https://railway.com/deploy/chirp-changelog?referralCode=KU30ob&utm_medium=integration&utm_source=template&utm_campaign=generic),
[Launch Board](https://railway.com/deploy/chirp-launch-board?referralCode=KU30ob&utm_medium=integration&utm_source=template&utm_campaign=generic),
or [Hookbox](https://railway.com/deploy/chirp-hookbox?referralCode=KU30ob&utm_medium=integration&utm_source=template&utm_campaign=generic).

## Status and ecosystem

Chirp is **alpha**. Its core model is ready to build with; APIs, scaffolds, and
the surrounding toolchain can still change. Check the [Public API](docs/public-api.md),
[reference](https://lbliii.github.io/chirp/docs/reference/), and changelog before
upgrading.

Chirp is the web framework in the Bengal ecosystem: [Bengal](https://github.com/lbliii/bengal)
builds static sites; [Purr](https://github.com/lbliii/purr) provides content runtime;
[chirp-ui](https://github.com/lbliii/chirp-ui) is the optional companion UI layer;
[Pounce](https://github.com/lbliii/pounce) serves ASGI; [Kida](https://github.com/lbliii/kida)
renders templates; [Patitas](https://github.com/lbliii/patitas) parses Markdown; and
[Rosettes](https://github.com/lbliii/rosettes) highlights syntax.

## License

MIT
