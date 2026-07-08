---
title: Hypermedia Model
description: "The mental model: HTML over the wire, content negotiation, and why the return type is the intent."
draft: false
weight: 10
lang: en
type: doc
tags: ["hypermedia", "content negotiation", "html over the wire", "fragment"]
keywords: ["hypermedia", "content negotiation", "html over the wire", "fragment", "return type"]
category: explanation
---

## What "hypermedia model" means

Chirp sends **HTML over the wire** — full pages, page fragments, and streamed
HTML — instead of JSON that a client framework turns into HTML. The server owns
rendering. The browser (often with [htmx](https://htmx.org)) swaps the HTML it
receives into the page. There is no client-side state store, no serialization
layer, and no separate API to keep in sync with the UI.

That leaves one question for every route: *which slice of HTML should this
request get?* Chirp answers it from the value your handler returns. **The return
type is the intent.**

```python
@app.route("/")
def index():
    return "Hello, World!"          # -> 200 text/html

@app.route("/api/status")
def status():
    return {"status": "ok"}         # -> 200 application/json
```

You never call `make_response()` or `jsonify()`. You return a value; Chirp turns
it into the right response. If you have ever returned `render_template(...)` in
Flask and reached for `jsonify(...)` on the next line, this is the same idea with
the wiring removed.

## Three things a request can ask for

A hypermedia app serves the *same* template at different scopes depending on who
is asking. Chirp recognises three render intents.

:::{list-table}
:header-rows: 1

* - Intent
  - The request looks like
  - Chirp sends
* - **Full page**
  - A browser navigation — no htmx
  - The whole template, layout and all
* - **Page fragment**
  - An htmx navigation (`hx-boost`, history restore)
  - A self-contained page region, no outer chrome
* - **Local fragment**
  - A narrow htmx swap (`hx-get` into a target)
  - A single named [[docs/build-apps/html-fragments/fragment-blocks|template block]]
:::

A template block is a named region of a template
(`{% block results %}…{% endblock %}`). The novelty
of the hypermedia model is that one template, with named blocks, serves *all
three* intents — there is no separate "partials" directory and no API view to
maintain alongside the page.

## Content negotiation: how Chirp decides

Chirp picks the intent from the request, so most handlers never branch on it
themselves. Two signals drive the decision:

1. **The return type** you chose — `Template`, `Fragment`, `Page`, and the rest.
2. **The `HX-Request` header** htmx sends on every request it issues.

The clearest expression of this is the `Page` return type. You hand it one
template and one block name; it renders the full page for a browser and just the
block for htmx — no `if` statement in your handler.

```python
from chirp import App, Page, Request

app = App()

@app.route("/search")
def search(request: Request):
    books = run_search(request.query.get("q", ""))
    return Page("search.html", "results", books=books)
```

A browser hitting `/search` gets `search.html` rendered in full. An htmx request
swapping `#results` gets only the `results` block — same handler, same template,
same data. Chirp adds `Vary: HX-Request, HX-Request-Type` so a cache never serves
a fragment to a browser, replays the wrong htmx 4 fragment width, or serves a
full page to a narrow target.

:::{tip}
`Page` is the negotiating type; `Template` is the always-full-page type. If you
write `Page("page.html", **ctx)` with no block name, you almost certainly want
`Template("page.html", **ctx)`. Chirp raises a guided `TypeError` to point you at
the right one.
:::

## The return-type vocabulary

Every render intent and transport has a return type. You pick the type that names
your intent; Chirp handles status codes, headers, and content negotiation.

:::{list-table}
:header-rows: 1

* - You want
  - You return
* - A full page rendered from a template
  - `Template("page.html", **ctx)`
* - One named block, no full page
  - `Fragment("page.html", "block", **ctx)`
* - Full page for browsers, fragment for htmx
  - `Page("page.html", "block", **ctx)`
* - Several swap targets in one response
  - `OOB(main, *oob_fragments)`
* - A shell now, slow sections streamed in
  - `Suspense("page.html", stats=load())`
* - A live channel after the page loads
  - `EventStream(generator())`
* - Plain HTML or JSON
  - a `str` or a `dict`
:::

This is the heart of the framework, and it has its own page. The full catalog —
every type, its signature, and a decision tree for choosing between them — lives
in [[docs/about/core-concepts/return-values|Return Values]].

## From return intent to application contract

Return types are also compiler input. At application freeze, Chirp combines
route declarations, typed return metadata, template blocks, htmx targets, and
registries into one immutable internal application model. `app.check()` uses
that model to catch detectable broken edges before a request reaches the
browser; runtime traces, DevTools, and transition tests correlate observed
requests with the same compiled transitions.

The compiler does not replace request-time rendering. SQL, forms, sessions,
streaming, and SSE still run in the live ASGI application. Static export through
`chirp freeze` is optional and applies only to compatible routes. See
[[docs/about/architecture|Architecture]] and the tested
[[docs/tutorials/full-application-journey|Full-Application Journey]] for the
complete feedback loop.

:::{note} See also

- [[docs/build-apps/html-fragments/fragments|Fragments]] — render named blocks for htmx swaps
- [[docs/build-apps/streaming-updates/_index|Streaming Updates]] — the decision table for `Stream` vs `Suspense` vs `EventStream`
:::

## Why HTML over the wire

The mental model pays off because the parts that usually drift cannot drift here.

- **One source of truth for the UI.** The HTML a browser sees and the HTML an
  htmx swap receives come from the same template and the same handler. There is
  no second JSON representation to keep aligned with the markup.
- **State lives on the server.** The page reflects server state directly, so you
  do not reconcile a client store against the database on every interaction.
- **Progressive enhancement is the default.** A route that returns a `Page` works
  as a plain HTML form without JavaScript; htmx upgrades it to a partial swap
  when present.

### No client-config blob to keep in sync

The clearest cost of the JSON/SPA model is the hand-maintained client-config
contract. A SPA cannot render until it knows what the server enabled, so the
server hand-builds a config blob the client fetches on boot — and then re-states
every one of those flags again on the admin side so they can be read and written
over the wire.

[open-webui](https://github.com/open-webui/open-webui) is a representative
example. Its `GET /api/config` handler returns a role-gated dictionary of server
flags the SPA fetches before it can render
(`backend/open_webui/main.py:2367`, returning a ~140-line dict through
`main.py:2539`). Editing those same flags needs a second surface:
`backend/open_webui/routers/configs.py` declares Pydantic `*ConfigForm` models
and paired `GET`/`POST` admin handlers — ~20 route handlers restating the same
field names (`configs.py:71` onward). A single flag like `enable_channels` is
typed in the Pydantic model, read in the GET handler, written in the POST
handler, and emitted in the boot blob — four hand-aligned restatements that must
not drift.

In Chirp the server-known flag is a value in the render context, consumed
directly in the template at render time. There is no boot blob and no
client-config contract — the flag and the markup that depends on it live in the
same place:

```python
import os

from chirp import App

app = App()

# Your own server-side flag — env var, settings object, feature service, etc.
FEATURE_CHANNELS = os.environ.get("FEATURE_CHANNELS") == "1"

# Make it available to every template (or pass it per-route as render context,
# or via a pages `_context.py` provider).
@app.template_global("enable_channels")
def enable_channels() -> bool:
    return FEATURE_CHANNELS
```

```html
{% if enable_channels %}
  <a href="/channels" class="nav-link">Channels</a>
{% endif %}
```

The flag is read where it is used. There is no `/api/config` endpoint to write,
no Pydantic form to keep aligned with it, and no client store to reconcile — the
contract the SPA had to maintain by hand simply does not exist. This is the
concrete shape of "no serialization layer." For the trade-offs of the JSON bet
as a whole, see [[docs/about/comparison|Comparison]].

For the design reasoning behind these choices, see
[[docs/about/philosophy|Philosophy]]; for the trade-offs versus a JSON/SPA stack,
see [[docs/about/comparison|Comparison]].

## Gotchas

:::{warning}
`request.is_fragment` is deprecated and ambiguous for boosted navigations. When
you genuinely need to branch by hand, use `request.is_htmx` (any htmx request) or
`request.is_narrow_fragment` (a narrow swap, excluding `hx-boost` and history
restore). Better: return a `Page` and let content negotiation make the decision
for you.
:::

## Going deeper

::::{dropdown} How Chirp computes the render intent
For `Page`, `LayoutPage`, and `PageComposition` returns, Chirp builds a
`RenderPlan` before any HTML is produced. The plan resolves to one of three
intents — `"full_page"`, `"page_fragment"`, or `"local_fragment"` — based on the
`HX-Request` header, whether the request is a boosted navigation or a history
restore, and the `HX-Target` of the swap.

Middleware can read the plan with `get_render_plan(request)` to log or act on the
rendering decision. The full mechanism, including layout-chain matching, is
covered in [[docs/build-apps/request-pipeline/render-plan|RenderPlan Middleware]].
::::{/dropdown}

## Next steps

- [[docs/about/core-concepts/return-values|Return Values]] — the full return-type catalog and decision tree
- [[docs/get-started/first-fragment-app|Your First Fragment App]] — build the negotiation loop end to end
- [[docs/build-apps/html-fragments/fragments|Fragments]] — the working surface for HTML over the wire
- [[docs/about/core-concepts/contracts|Contracts]] — how `app.check()` validates this wiring at startup

:::{related}
:::
