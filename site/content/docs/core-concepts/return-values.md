---
title: Return Values
description: All the types route handlers can return and what they mean
draft: false
weight: 20
lang: en
type: doc
tags: [return-values, content-negotiation, types]
keywords: [return, template, fragment, stream, eventstream, response, redirect]
category: explanation
---

## The Type Is the Intent

Route functions return *values*. Chirp handles content negotiation based on the return type -- no `make_response()`, no `jsonify()`, no explicit content-type wiring.

```python
return "Hello"                                       # -> 200, text/html
return {"users": [...]}                              # -> 200, application/json
return Template("page.html", title="Home")           # -> 200, rendered via kida
return Template.inline("<h1>{{ t }}</h1>", t="Hi")   # -> 200, from string
return Fragment("page.html", "results", items=x)     # -> 200, rendered block
return Stream("dashboard.html", **async_ctx)         # -> 200, streamed HTML
return Suspense("dashboard.html", stats=get_stats()) # -> 200, shell + OOB swaps
return EventStream(generator())                      # -> SSE stream
return Response(body=b"...", status=201)              # -> explicit control
return hx_redirect("/dashboard")                      # -> Location + HX-Redirect
return Redirect("/login")                            # -> 302
```

## InlineTemplate (Prototyping)

Renders a template from a string instead of a file. Useful for prototyping and scripts where you don't want to set up a `templates/` directory:

```python
from chirp import Template

@app.route("/")
def index():
    return Template.inline("<h1>{{ greeting }}</h1>", greeting="Hello, world!")
```

`Template.inline()` returns an `InlineTemplate` instance. It works through content negotiation without requiring a `template_dir` to be configured.

:::{note}
`InlineTemplate` is a prototyping shortcut. `app.check()` will emit a warning for routes that return it. Replace with file-based `Template` before production.
:::

## Template

Renders a full template via kida:

```python
from chirp import Template

@app.route("/")
def index():
    return Template("index.html", title="Home", items=items)
```

The first argument is the template path (relative to your `template_dir`). Everything else becomes template context.

**Auto-injected context:** Chirp automatically adds `current_path` (set to `request.path`) to the template context when it is not already present. This means ChirpUI navigation components like `sidebar_link(..., match="prefix")` and `navbar_link(..., match="exact")` work without manually passing `current_path` or `nav=` strings from every handler.

## Fragment

Renders a named block from a template, without rendering the full page:

```python
from chirp import Fragment

@app.route("/search")
def search(request: Request):
    results = do_search(request.query.get("q", ""))
    if request.is_fragment:
        return Fragment("search.html", "results_list", results=results)
    return Template("search.html", results=results)
```

This is Chirp's key differentiator. Same template, same data, different scope. See [[docs/templates/fragments|Fragments]] for the full story.

## Page

Auto-detects whether to return a full page or a fragment based on the request:

```python
from chirp import Page

@app.route("/search")
def search(request: Request):
    results = do_search(request.query.get("q", ""))
    return Page("search.html", "results_list", results=results)
```

`Page` is sugar over the `if request.is_fragment` pattern. If the request comes from htmx, it renders the block. Otherwise, it renders the full template.

Use `page_block_name` when boosted page navigation needs a wider, fragment-safe root than the narrow fragment block:

```python
from chirp import Page

@app.route("/dashboard")
def dashboard():
    return Page(
        "dashboard.html",
        "results_panel",
        page_block_name="page_root",
        stats=load_stats(),
    )
```

This keeps ordinary fragment requests narrow (`results_panel`) while boosted navigation can swap a self-contained page root (`page_root`) that includes layout wrappers such as stacks, toolbars, and section spacing.

:::{note}
**LayoutPage** and **LayoutSuspense** are internal types used when filesystem routing renders through layout chains. Handlers return `Page` or `Suspense`; Chirp upgrades them when layouts are involved. You typically don't construct these directly.
:::

## PageComposition

Python-first composition API for explicit page structure. Use `fragment_block` and `page_block` instead of `block_name` / `page_block_name`, and add optional region updates for shell actions:

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

`Page` and `LayoutPage` are normalized to `PageComposition` internally; both APIs work. Use `PageComposition` when you want explicit region updates or clearer semantics.

## Stream

Progressive HTML rendering. The browser receives the page shell immediately and content fills in as data becomes available:

```python
from chirp import Stream

@app.route("/dashboard")
async def dashboard():
    return Stream("dashboard.html",
        header=site_header(),
        stats=await load_stats(),
        activity=await load_activity(),
    )
```

See [[docs/streaming/html-streaming|Streaming HTML]] for details.

## Suspense

Instant first paint with deferred data. The browser receives the full page shell immediately (with skeleton placeholders), then the actual content streams in as OOB swaps once each data source resolves:

```python
from chirp import Suspense

@app.route("/dashboard")
async def dashboard():
    return Suspense("dashboard.html",
        stats=get_stats(),       # awaitable — deferred, shell shows skeleton
        orders=get_orders(),     # awaitable — deferred, shell shows skeleton
        title="Sales Dashboard", # plain value — available in the shell
    )
```

The template uses `{% if stats %}...{% else %}skeleton{% end %}` inside named blocks. Chirp renders the shell with `None` for awaitable keys (triggering the skeleton branch), resolves the awaitables concurrently, then streams each block's real content as an OOB swap.

See [[docs/streaming/html-streaming|Streaming HTML]] for the full story.

## EventStream

Server-Sent Events. Push data to the browser over a persistent connection:

```python
from chirp import EventStream, Fragment

@app.route("/notifications")
async def notifications():
    async def stream():
        async for event in notification_bus.subscribe():
            yield Fragment("components/notification.html", event=event)
    return EventStream(stream())
```

The generator yields values (strings, dicts, Fragments, or SSEEvents). See [[docs/streaming/server-sent-events|Server-Sent Events]] for details.

## Response

Explicit control over the HTTP response:

```python
from chirp import Response

@app.route("/api/create")
async def create():
    return Response(body=b'{"id": 42}', status=201).with_header(
        "Content-Type", "application/json"
    )
```

Response supports a chainable `.with_*()` API. See [[docs/routing/request-response|Request & Response]].

## Redirect

```python
from chirp import Redirect

@app.route("/old-page")
def old_page():
    return Redirect("/new-page")  # 302 by default
```

Use `Redirect(...)` when you want a normal HTTP redirect and do not need to
shape the response further.

## hx_redirect

`hx_redirect()` is a response helper for handlers that may be reached by either
plain browser navigation or htmx requests:

```python
from chirp import hx_redirect

@app.route("/login", methods=["POST"])
async def login(request: Request):
    # ... authenticate ...
    return hx_redirect("/dashboard")
```

It returns a `Response` with both:

- `Location: /dashboard` for normal browser redirects
- `HX-Redirect: /dashboard` for htmx full-page navigation

Use it when the same handler services both progressive enhancement paths and you
want one return value that works cleanly for both.

## MutationResult

Progressive enhancement for any mutation (POST, PUT, PATCH, DELETE). Auto-negotiates htmx vs non-htmx: htmx requests get rendered fragments, non-htmx requests get a redirect.

```python
from chirp import MutationResult, Fragment

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

- **Non-htmx**: 303 redirect to the URL (fragments are ignored)
- **htmx + fragments**: renders the fragments, adds `HX-Trigger` if set
- **htmx + no fragments**: sends `HX-Redirect` header

Works for all mutation methods, not just form POST:

```python
@app.route("/items/{item_id}", methods=["DELETE"])
async def delete_item(item_id: int):
    _delete_item(item_id)
    items = _get_items()
    return MutationResult(
        "/items",
        Fragment("items.html", "list", items=items),
        trigger="itemDeleted",
    )
```

Simple redirect for both modes:

```python
return MutationResult("/dashboard")
```

:::{note}
`FormAction` is a backwards-compatible alias for `MutationResult`. Both names work identically.
:::

## Strings and Dicts

Plain strings are returned as `text/html`. Dicts are serialized as JSON:

```python
@app.route("/hello")
def hello():
    return "Hello, World!"  # text/html, 200

@app.route("/api/status")
def status():
    return {"status": "ok"}  # application/json, 200
```

## ValidationError

Returns a 422 response with a rendered fragment, designed for form validation:

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

## OOB (Out-of-Band)

Sends multiple fragment updates in a single response -- the main content plus additional out-of-band swaps:

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

Combined with htmx's `hx-swap-oob`, this updates multiple parts of the page in one request.

## Choosing a Streaming Type

Chirp has three streaming return types. Use this decision tree:

| Question | Answer | Type |
|----------|--------|------|
| Does your template use `{% async for %}` or `{{ await }}`? | Yes | **TemplateStream** |
| Do you want a skeleton/shell rendered instantly, with slow data filling in later? | Yes | **Suspense** |
| Do you just want chunked transfer of a large page? | Yes | **Stream** |

**Stream** -- All data resolves upfront (concurrently), then chunks stream out. Best for large templates where you want the browser painting before the full HTML is ready.

**TemplateStream** -- The template itself consumes an async iterator during rendering. One pass, O(n). Ideal for LLM token streaming and long async feeds.

**Suspense** -- Shell renders instantly with skeletons, then slow blocks fill in as OOB swaps. Best for dashboards with multiple independent slow data sources.

See [[docs/streaming/html-streaming|Streaming HTML]] for the full story.

## Introspecting Render Decisions

For `Page`, `LayoutPage`, and `PageComposition` returns, Chirp builds a `RenderPlan` that captures the rendering decision before HTML is produced. Middleware can inspect it:

```python
from chirp import get_render_plan

async def analytics_middleware(request, next):
    response = await next(request)
    plan = get_render_plan(request)
    if plan is not None:
        log_render_intent(plan.intent, plan.layout_start_index)
    return response
```

The `RenderPlan` is a frozen dataclass with fields for `intent` (`"full_page"`, `"page_fragment"`, `"local_fragment"`), layout chain depth, and region updates. See [[docs/guides/render-plan|RenderPlan Middleware Guide]] for practical patterns.

## Next Steps

- [[docs/templates/fragments|Fragments]] -- Deep dive into fragment rendering
- [[docs/templates/rendering|Rendering]] -- Template rendering in detail
- [[docs/routing/request-response|Request & Response]] -- The chainable Response API
- [[docs/guides/tools|Tools & MCP]] -- Register functions as MCP tools for AI agents
- [[docs/guides/render-plan|RenderPlan Middleware]] -- Inspect rendering decisions from middleware
