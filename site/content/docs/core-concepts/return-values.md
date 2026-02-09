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
return "Hello"                                   # -> 200, text/html
return {"users": [...]}                          # -> 200, application/json
return Template("page.html", title="Home")       # -> 200, rendered via kida
return Fragment("page.html", "results", items=x) # -> 200, rendered block
return Stream("dashboard.html", **async_ctx)     # -> 200, streamed HTML
return EventStream(generator())                  # -> SSE stream
return Response(body=b"...", status=201)          # -> explicit control
return Redirect("/login")                        # -> 302
```

## Template

Renders a full template via kida:

```python
from chirp import Template

@app.route("/")
def index():
    return Template("index.html", title="Home", items=items)
```

The first argument is the template path (relative to your `template_dir`). Everything else becomes template context.

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

## Next Steps

- [[docs/templates/fragments|Fragments]] -- Deep dive into fragment rendering
- [[docs/templates/rendering|Rendering]] -- Template rendering in detail
- [[docs/routing/request-response|Request & Response]] -- The chainable Response API
