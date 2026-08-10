---
title: Return Values
description: All the types route handlers can return and what they mean
draft: false
weight: 70
lang: en
type: doc
tags: [return-values, content-negotiation, types]
keywords: [return, template, fragment, stream, eventstream, response, redirect]
category: explanation
---

## The type is the intent

Every route handler returns a *value*, and the type of that value is the intent. `Template` means a full page, `Fragment` means one named [[docs/build-apps/html-fragments/fragment-blocks|template block]], `Page` lets Chirp choose between them based on the request, and a handful of others cover streaming, redirects, and mutations.

Chirp reads the return type and does [[docs/about/core-concepts/hypermedia-model|content negotiation]] — picking full-page versus fragment, composing layouts, and adding htmx headers — for you. No `make_response()`, no `jsonify()`, no manual content-type wiring.

```python
return "Hello"                                       # -> 200, text/html
return {"users": [...]}                              # -> 200, application/json
return Template("page.html", title="Home")           # -> 200, full page via kida
return Fragment("page.html", "results", items=x)     # -> 200, one rendered block
return Page("page.html", "results", **ctx)           # -> full page or block (auto)
return Suspense("dashboard.html", stats=get_stats()) # -> 200, shell + OOB swaps
return Stream("dashboard.html", **async_ctx)         # -> 200, streamed HTML
return EventStream(generator())                      # -> SSE stream
return MutationResult("/contacts", *fragments)       # -> fragments (htmx) or 303
return ValidationError("page.html", "form", errors=e)# -> 422 + re-rendered form
return Redirect("/login")                            # -> 302
```

This page is the map. Use the decision table to find your return type, then jump to that type's section.

## Pick a return type

:::{list-table} What do you want to return?
:header-rows: 1

* - I want to…
  - Return type
* - Render a full page (no htmx awareness)
  - `Template("page.html", **ctx)`
* - Render one named block of a template
  - `Fragment("page.html", "block", **ctx)`
* - Serve a full page to browsers *and* a fragment to htmx, from one handler
  - `Page("page.html", "block", **ctx)`
* - Update several swap targets in one response
  - `OOB(main, *oob_fragments)`
* - Paint a shell instantly, then stream slow sections in
  - `Suspense("page.html", stats=get_stats())`
* - Stream page sections as they finish (no shell-first)
  - `Stream("page.html", **async_ctx)`
* - Push updates after the page has loaded
  - `EventStream(async_generator())`
* - Re-render a form with validation errors
  - `ValidationError("page.html", "form", errors=e)`
* - Handle a mutation: fragments for htmx, redirect for plain POST
  - `MutationResult(url, *fragments)`
* - Redirect
  - `Redirect("/login")` (plain) or `hx_redirect("/dashboard")` (htmx-aware)
:::

:::{tip} `Page` vs `Template` — the common mixup
`Page` needs a block name because it serves *two* modes: the full template for browsers, the block for htmx. If you reach for `Page("page.html", **ctx)` with no block name, you want `Template("page.html", **ctx)` — the plain full-page render. `Page` raises a guided `TypeError` to nudge you toward the right type.
:::

## Template

Renders a full template via [[docs/build-apps/html-fragments/kida-integration|Kida]]:

```python
from chirp import Template

@app.route("/")
def index():
    return Template("index.html", title="Home", items=items)
```

The first argument is the template path (relative to your `template_dir`). Everything else becomes template context.

Chirp auto-injects `current_path` (set to `request.path`) into the context when you haven't set it. ChirpUI navigation components like `sidebar_link(..., match="prefix")` then work without passing `current_path` from every handler.

## Fragment

Renders a named block from a template without rendering the full page:

```python
from chirp import Fragment

@app.route("/results")
def results(request: Request):
    return Fragment("search.html", "results_list", results=do_search(request))
```

Same template, same data, narrower scope. This is Chirp's core move — one template serves both the full page and the htmx swap. See [[docs/build-apps/html-fragments/fragments|Fragments]] for the full story.

## Page

Auto-detects whether to return a full page or a fragment based on the request — full template for a browser, block for an htmx swap:

```python
from chirp import Page

@app.route("/search")
def search(request: Request):
    results = do_search(request.query.get("q", ""))
    return Page("search.html", "results_list", results=results)
```

`Page` is the preferred way to negotiate full-page versus fragment. Reach for it instead of branching on a request flag by hand.

:::{warning} Don't branch on `request.is_fragment`
`request.is_fragment` is **deprecated** — it's ambiguous for boosted navigations and emits a `DeprecationWarning`. Let `Page` negotiate for you. If you must branch by hand, use `request.is_htmx` (any htmx request) or `request.is_narrow_fragment` (a narrow swap, excluding boosted navigation and history restores).
:::

::::{dropdown} Boosted navigation: a wider fragment-safe root (`page_block_name`)
When [[docs/build-apps/ui-extensions/boosted-navigation|boosted navigation]] swaps a whole page, a narrow fragment block can be too small — it omits layout wrappers. Pass `page_block_name` to give boosted swaps a wider, self-contained root while ordinary fragment requests stay narrow:

```python
@app.route("/dashboard")
def dashboard():
    return Page(
        "dashboard.html",
        "results_panel",       # narrow block for ordinary fragment requests
        page_block_name="page_root",  # wider root for boosted navigation
        stats=load_stats(),
    )
```
::::{/dropdown}

:::{note}
`LayoutPage` and `LayoutSuspense` are internal types Chirp uses when [[docs/build-apps/pages-navigation/filesystem-routing|filesystem routing]] renders through layout chains. You return `Page` or `Suspense`; Chirp upgrades them when layouts are involved. You don't construct these directly.
:::

## Suspense

Paints the shell instantly, then streams real content in as each slow data source resolves. The browser gets the full page with skeleton placeholders, then [[docs/build-apps/html-fragments/fragments|OOB swaps]] fill them in:

```python
from chirp import Suspense

@app.route("/dashboard")
async def dashboard():
    return Suspense("dashboard.html",
        stats=get_stats(),       # awaitable -> deferred, shell shows skeleton
        orders=get_orders(),     # awaitable -> deferred, shell shows skeleton
        title="Sales Dashboard", # plain value -> available in the shell
    )
```

In the template, branch on **`{% if stats is deferred %}`** — not bare `{% if stats %}`, which reads an empty resolved `tuple`/`list` as "still loading":

```html
{% if stats is deferred %}
  <div class="skeleton">Loading…</div>
{% else %}
  {{ render_stats(stats) }}
{% end %}
```

Chirp resolves the awaitables concurrently, then streams each affected block as an OOB swap. Blocks are discovered automatically by static analysis. Two optional parameters override that:

- **`defer_blocks`** — an explicit tuple of block names to re-render, bypassing analysis. Use it when deferred values pass through macro arguments the analyzer can't trace.
- **`defer_map`** — maps a block name to a different DOM id for the swap target, e.g. `{"stats": "stats-panel"}`.

When deferred loaders check out PostgreSQL connections from Chirp's Pelt pool (via `Database` or `Pool.acquire`), each independent defer holds its **own** connection for the duration of that awaitable. Connections are never shared across concurrent defers. If more independent defers need a checkout than `pool_size` allows, excess `acquire()` calls **wait** until a sibling releases — queueing latency, not a shared borrow. Size `pool_size` to the peak concurrent independent checkouts you need, and release promptly inside each defer (do not hold a checkout across unrelated awaits between defers).

::::{dropdown} Advanced: the deferred sentinel and pending-key set
`is deferred` is the rule you need. Under the hood, the shell sets each unresolved awaitable key to the `DEFERRED` sentinel, and sets `__chirp_defer_pending__` to a `frozenset` of keys still awaiting resolution (empty once resolved, or when there were no awaitables). You can branch on `"stats" in __chirp_defer_pending__` if you prefer the pending-key set. The constant `CHIRP_DEFER_PENDING_KEY` holds the string `"__chirp_defer_pending__"`. These are provisional extension surfaces; prefer `is deferred` in templates.
::::{/dropdown}

See [[docs/build-apps/streaming-updates/html-streaming|Streaming HTML]] for the full mechanism.

## Stream

Progressive HTML rendering with no shell-first step. Pass awaitable context values unawaited — Chirp resolves them concurrently up front, then the page chunks out so the browser paints before the full HTML is ready:

```python
from chirp import Stream

@app.route("/dashboard")
async def dashboard():
    return Stream("dashboard.html",
        header=site_header(),     # plain value
        stats=load_stats(),       # coroutine -> resolved concurrently
        activity=load_activity(), # coroutine -> resolved concurrently
    )
```

:::{note} Stream vs Suspense vs TemplateStream
Chirp has three streaming return types. `Stream` chunks a page after data resolves; `Suspense` paints a shell first and fills slow blocks via OOB swaps; `TemplateStream` lets the template itself consume an async iterator (ideal for LLM token streaming). See [[docs/build-apps/streaming-updates/html-streaming|Streaming HTML]] for the full decision.
:::

## EventStream

Server-Sent Events — push updates to the browser over a persistent connection *after* the page has loaded:

```python
from chirp import EventStream, Fragment

@app.route("/notifications")
async def notifications():
    async def stream():
        async for event in notification_bus.subscribe():
            yield Fragment("components/notification.html", "item", event=event)
    return EventStream(stream())
```

The generator yields values — strings, dicts, `Fragment`s, or `SSEEvent`s. See [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]] and [[docs/build-apps/streaming-updates/sse-patterns|SSE patterns]] for the wire format and recipes.

## MutationResult

Progressive enhancement for any mutation (POST, PUT, PATCH, DELETE). htmx requests get rendered fragments; plain requests get a redirect:

```python
from chirp import MutationResult, Fragment

# ContactForm is a form shape; Chirp extracts it from the request body
# by the typed parameter annotation. See Forms & validation.
@app.route("/contacts", methods=["POST"])
async def add_contact(form: ContactForm):
    _add_contact(form.name, form.email)
    contacts = _get_contacts()
    return MutationResult(
        "/contacts",
        Fragment("contacts.html", "table", contacts=contacts),
        Fragment("contacts.html", "count", target="count", count=len(contacts)),
        trigger="contactAdded",
    )
```

- **Plain request:** 303 redirect to the URL (fragments ignored)
- **htmx + fragments:** renders the fragments, adds `HX-Trigger` if `trigger` is set
- **htmx + no fragments:** sends an `HX-Redirect` header

It works for every mutation method, not just form POST — a `DELETE` handler returning a refreshed list works the same way. For a redirect in both modes, return `MutationResult("/dashboard")` with no fragments.

:::{note}
`FormAction` is a backwards-compatible alias for `MutationResult` — same class, different name.
:::

## ValidationError

Returns a 422 with a re-rendered form fragment — the standard htmx form-validation loop:

```python
from chirp import ValidationError

@app.route("/submit", methods=["POST"])
async def submit(request: Request):
    form = await request.form()
    errors = validate(form)
    if errors:
        return ValidationError("form.html", "form_errors", errors=errors)
    # ... process valid form
```

See [[docs/build-apps/forms-data/forms-validation|Forms & validation]] for the full pattern.

## OOB (out-of-band)

Updates several parts of the page in one response — a main fragment plus extra out-of-band swaps:

```python
from chirp import OOB, Fragment

@app.route("/update")
def update():
    return OOB(
        Fragment("page.html", "main_content", data=data),
        Fragment("page.html", "sidebar", stats=stats),
        Fragment("page.html", "notification_count", count=count),
    )
```

Combined with htmx's `hx-swap-oob`, this swaps multiple regions from a single request.

## Redirect and hx_redirect

`Redirect` is a normal HTTP redirect (302 by default):

```python
from chirp import Redirect

@app.route("/old-page")
def old_page():
    return Redirect("/new-page")
```

`hx_redirect` handles a handler reachable by *either* plain browser navigation or htmx. It returns a `Response` carrying both `Location` (for browser redirects) and `HX-Redirect` (for htmx full-page navigation):

```python
from chirp import hx_redirect

@app.route("/login", methods=["POST"])
async def login(request: Request):
    # ... authenticate ...
    return hx_redirect("/dashboard")
```

## Strings, dicts, and Response

Plain strings return as `text/html`; dicts serialize to JSON:

```python
@app.route("/hello")
def hello():
    return "Hello, World!"      # text/html, 200

@app.route("/api/status")
def status():
    return {"status": "ok"}     # application/json, 200
```

For full control, return a `Response` with a chainable `.with_*()` API:

```python
from chirp import Response

@app.route("/api/create")
async def create():
    return Response(body=b'{"id": 42}', status=201).with_header(
        "Content-Type", "application/json"
    )
```

See [[docs/build-apps/pages-navigation/request-response|Request & Response]] for the chainable API.

## InlineTemplate (prototyping)

`Template.inline()` renders a template from a string instead of a file — a prototyping shortcut for scripts where you don't want a `templates/` directory yet:

```python
from chirp import Template, InlineTemplate

@app.route("/")
def index() -> InlineTemplate:
    return Template.inline("<h1>{{ greeting }}</h1>", greeting="Hello, world!")
```

:::{warning} Replace before production
`app.check()` warns on any route annotated to return an `InlineTemplate` (it inspects the handler's `-> InlineTemplate` return annotation, not its runtime return value). Move to a file-based `Template` before you ship.
:::

## Advanced and internal

::::{dropdown} Explicit page composition (`PageComposition`)
`PageComposition` is a Python-first API for explicit page structure, with optional region updates for shell actions. `Page` is normalized to it internally — reach for it only when you want explicit region updates.

```python
from chirp import PageComposition, RegionUpdate, ViewRef

@app.route("/skills")
def skills():
    return PageComposition(
        template="skills/page.html",
        fragment_block="page_content",
        page_block="page_root",
        context={"skills": skills},
        regions=(
            RegionUpdate(
                region="shell_actions",
                view=ViewRef(
                    template="chirp/shell_actions.html",
                    block="content",
                    context={"shell_actions": actions},
                ),
            ),
        ),
    )
```

`PageComposition`, `RegionUpdate`, and `ViewRef` are advanced introspection APIs (debug-stability) — not part of the everyday return surface.
::::{/dropdown}

::::{dropdown} Inspect render decisions from middleware (`get_render_plan`)
For `Page` and `PageComposition` returns, Chirp builds a `RenderPlan` capturing the rendering decision before HTML is produced. Middleware can read it:

```python
from chirp import get_render_plan

async def analytics_middleware(request, next):
    response = await next(request)
    plan = get_render_plan(request)
    if plan is not None:
        log_render_intent(plan.intent, plan.layout_start_index)
    return response
```

`RenderPlan.intent` is one of `"full_page"`, `"page_fragment"`, or `"local_fragment"`. `get_render_plan` and `RenderPlan` are advanced introspection APIs (debug-stability). See the [[docs/build-apps/request-pipeline/render-plan|RenderPlan middleware guide]] for patterns.
::::{/dropdown}

:::{note} See also

- [[docs/examples/returns-gallery|Returns gallery]] — runnable examples of every return type
- [[docs/get-started/first-fragment-app|Build your first fragment loop]] — the smallest full-page → fragment round trip
- [[docs/build-apps/html-fragments/fragments|Fragments]] — deep dive into fragment rendering
- [[docs/build-apps/streaming-updates/html-streaming|Streaming HTML]] — Stream vs Suspense vs TemplateStream
- [[docs/build-apps/pages-navigation/request-response|Request & Response]] — the chainable Response API
:::

:::{related}
:::
