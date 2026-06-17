---
title: Errors
description: Error hierarchy, error handlers, and debug pages
draft: false
weight: 20
lang: en
type: doc
tags: [errors, exceptions, error-handling, debug]
keywords: [errors, exceptions, chirperror, httperror, notfound, error-handler, debug]
category: reference
---

Chirp's exceptions all inherit from `ChirpError`. You have two jobs: **raise**
an HTTP error (`NotFound`, `HTTPError`) inside a handler to send an error
response, and **register** `@app.error` handlers to control what the reader
sees. This page is the reference for the error types, the handler signatures,
and the dev-mode error output.

## Error hierarchy

All Chirp exceptions subclass `ChirpError`. The HTTP errors are frozen
dataclasses that carry a `status` code and a `detail` string.

:::{list-table}
:header-rows: 1

* - Exception
  - Status
  - Raise it when
* - `ChirpError`
  - —
  - Base class. Catch it to handle any Chirp error.
* - `HTTPError`
  - any
  - You want to return a specific status: `raise HTTPError(403, "Forbidden")`.
* - `NotFound`
  - 404
  - A resource does not exist. Subclass of `HTTPError`.
* - `MethodNotAllowed`
  - 405
  - Raised automatically by the router when the path matches but the method does not.
* - `PayloadTooLarge`
  - 413
  - Raised automatically when a request body or upload exceeds a configured size limit.
* - `ConfigurationError`
  - —
  - The app is misconfigured. Raised at startup, before any request is served.
:::

## Raising errors

Raise HTTP errors in route handlers to trigger error responses:

```python
from chirp import NotFound, HTTPError, g

@app.route("/users/{id:int}")
async def get_user(id: int):
    user = await db.fetch_one("SELECT * FROM users WHERE id = ?", [id])
    if not user:
        raise NotFound(f"User {id} not found")
    return Template("user.html", user=user)

@app.route("/premium")
def premium():
    # g.user / .is_premium here is your own app state, not a Chirp API.
    if not g.user or not g.user.is_premium:
        raise HTTPError(403, "Premium access required")
    return Template("premium.html")
```

`g` is Chirp's [[docs/build-apps/pages-navigation/request-response|request-scoped state]] —
populate it from your auth middleware.

### NotFound

```python
raise NotFound("Page not found")     # 404 with detail message
raise NotFound()                       # 404 with default message
```

### MethodNotAllowed

Raised automatically by the router when a path matches but the HTTP method does not. The response includes an `Allow` header listing valid methods and the allowed methods in the body.

### ConfigurationError

Raised at startup, before any request is served, for invalid configuration:

```python
# These raise ConfigurationError:
# - Adding SessionMiddleware without a secret_key
# - Adding CSRFMiddleware without SessionMiddleware
# - Returning Template/Fragment when kida integration is not configured
```

Most startup misconfiguration surfaces through `app.check()` rather than a raw
exception. See [[docs/quality/contracts-debugging/categories|startup contract checks]]
for the full catalog of what is validated and how severity is decided.

## Error handlers

Register custom error handlers by status code or exception type:

```python
@app.error(404)
def handle_404(request: Request):
    return Template("errors/404.html", path=request.path)

@app.error(500)
def handle_500(request: Request, error: Exception):
    return Template("errors/500.html", error=str(error))
```

Error handlers support the same return-value system as route handlers. You can return a `Template`, `Fragment`, `Response`, string, or dict.

### Handler signatures

Chirp inspects the handler signature and injects the appropriate arguments —
pick whichever fits. Sync and async handlers both work.

::::{code-tabs}
:sync: signature

```python
# No args
@app.error(404)
def handle_404():
    return "Not Found"
```

```python
# Request
@app.error(404)
def handle_404(request: Request):
    return Template("404.html", path=request.path)
```

```python
# Request + error
@app.error(500)
def handle_500(request: Request, error: Exception):
    log_error(error)
    return Template("500.html")
```
::::

### Exception-type handlers

Register a handler keyed on an exception class instead of a status code. The key
must be a real exception you `raise`. Chirp matches `type(exc)` first, then falls
back to the status code, so a type handler lets you centralize the response for
one domain error in one place:

```python
from chirp import HTTPError

class PaymentRequired(HTTPError):
    def __init__(self, detail: str = "Payment required"):
        super().__init__(402, detail)

@app.error(PaymentRequired)
def handle_payment(request: Request, error: PaymentRequired):
    return Template("errors/payment.html", detail=error.detail)
```

Raise `PaymentRequired(...)` anywhere in a handler and this handler renders the
response. Because the lookup is type-first, it wins over a `@app.error(402)`
status handler for that specific class.

:::{warning} `ValidationError` is a return type, not an exception
`ValidationError` from the
[[docs/build-apps/forms-data/forms-validation|forms and validation]] flow is a
return value — you `return` it, and the negotiation layer turns it into a 422
fragment. It is not an exception, so you cannot `raise` it and
`@app.error(ValidationError)` never fires. Centralize 422 handling by returning
`ValidationError` from a shared helper, not by registering an error handler.
:::

### Fragment-aware error handling

When an htmx request triggers an error, you usually want to swap a small error
[[docs/build-apps/html-fragments/fragments|fragment]] into the page instead of
replacing it with a full error document. The simplest way is to return a `Page`
and let Chirp negotiate: it renders the named block for a narrow htmx swap and
the full page for a browser navigation.

```python
@app.error(404)
def handle_404(request: Request):
    return Page("errors/404.html", "error_message", path=request.path)
```

If you need to branch explicitly, check `request.is_narrow_fragment` — `True`
only for a narrow swap, `False` for boosted navigations and history restores
that still need full page content:

```python
@app.error(404)
def handle_404(request: Request):
    if request.is_narrow_fragment:
        return Fragment("errors/404.html", "error_message", path=request.path)
    return Template("errors/404.html", path=request.path)
```

:::{warning} Do not use `request.is_fragment`
`request.is_fragment` is deprecated and emits a `DeprecationWarning` on every
access — it is `True` for *any* htmx request, including boosted navigations that
actually need a full page. Use `request.is_narrow_fragment` (narrow swap only)
or `request.is_htmx` (any htmx request) instead.
:::

When you do not register a handler, built-in error handling automatically
returns a `<div class="chirp-error">` snippet for htmx requests and a full
document otherwise.

## Dev-mode error output

During development, Chirp formats errors for the terminal with structured,
readable output instead of raw Python tracebacks. You rarely configure this — it
is on automatically in `debug` mode. The detail below is for when you want to
change the verbosity or understand how streaming errors are surfaced.

:::{dropdown} Terminal formatting and CHIRP_TRACEBACK
**Template errors.** When a Kida template error occurs, Chirp displays the error
with its code, source snippet, and route context:

```
-- Template Error -----------------------------------------------
K-RUN-001: Undefined variable 'usernme' in base.html:42

     |
> 42 | <h1>{{ usernme }}</h1>
     |

Hint: Did you mean 'username'?
Docs: https://kida.dev/docs/errors/#k-run-001

  Route: GET /dashboard
-----------------------------------------------------------------
```

**Non-template errors.** For other exceptions, Chirp filters tracebacks to show
only application frames, hiding framework and stdlib internals.

**Verbosity.** Control terminal traceback style with the `CHIRP_TRACEBACK`
environment variable:

| Value | Behavior |
|-------|----------|
| `compact` | App frames only (default) |
| `full` | Full Python traceback |
| `minimal` | Single-line error summary |

```bash
# Show full tracebacks during deep debugging
CHIRP_TRACEBACK=full chirp run myapp:app

# Minimal output for CI/production
CHIRP_TRACEBACK=minimal chirp run myapp:app
```
:::

:::{dropdown} Streaming and SSE error boundaries
Errors during chunked streaming or SSE connections use the same formatting
pipeline. In debug mode, streaming errors render as a visible
`<div class="chirp-error">` element in the page.

SSE streams have **per-event error boundaries**: if a single `Fragment` fails to
render, the error is caught and the stream continues. An error event is always
sent so the client knows an event was lost — only the payload differs. In debug
mode, the failed block is replaced with a `<div class="chirp-block-error">`
element showing the exception inline. In production, a generic `event: error`
("Event rendering failed") is sent instead of the inline block detail.

If the `context_builder()` in a reactive stream raises, the entire event is
skipped (logged via the `chirp.reactive` logger) and the stream waits for the
next change.

Catastrophic errors (ASGI failures, unrecoverable state) still terminate the
stream with an `event: error` message the client can handle.
:::

## Debug pages

When [`AppConfig(debug=True)`](/chirp/docs/about/core-concepts/configuration/),
unhandled exceptions render a full HTML debug page in the browser with the
traceback (framework frames collapsed), request details, app configuration, a
Kida template error panel, and an environment section showing the Python, Chirp,
and Kida versions. Consecutive framework frames are folded into an expandable
block to reduce noise.

:::{warning}
Debug pages expose internal details. Never enable `debug=True` in production.
:::

:::{note} See also
- [[docs/about/core-concepts/configuration|Configuration]] — `debug` mode and other `AppConfig` settings
- [[docs/build-apps/pages-navigation/routes|Routes]] — error handlers and route registration
- [[docs/quality/contracts-debugging/categories|Contract check categories]] — what `app.check()` validates at startup
- [[docs/reference/api|API Reference]] — the complete public API surface
:::
