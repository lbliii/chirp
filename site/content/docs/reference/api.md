---
title: API Reference
description: The searchable index of Chirp's public API — what to import, its one-line job, and how stable it is.
draft: false
weight: 10
lang: en
type: doc
tags: [reference, api, exports]
keywords: [api, reference, exports, chirp, public-api, types, stability]
category: reference
---

## Overview

Every public name lives on the top-level `chirp` package. This page is the
searchable index of that surface: what to import, its one-line job, and how
stable it is.

Names are grouped by maturity:

- **Stable** — safe to build on; the core you reach for every day.
- **Provisional** — works today, may shift between minor versions.
- **Debug / advanced** — introspection and internals you rarely import directly.

For field-by-field config see [[docs/about/core-concepts/configuration|Configuration]].
For the exception hierarchy see [[docs/reference/errors|Errors]]. For *which*
return type to reach for, see the [[docs/about/core-concepts/return-values|return-type decision tree]].

:::{tip}
The stable / provisional / debug split is not editorial flavor — it mirrors
Chirp's `chirp._API_STATUS` registry, which is enforced against the public-API
docs in CI. A name's tier tells you the compatibility promise attached to it.
:::

## Stable core

The 80% you import to build an app. Each name is importable directly from
`chirp`:

```python
from chirp import (
    # Application
    App,
    AppConfig,

    # HTTP
    Request,
    Response,
    Redirect,
    FileResponse,
    JSONResponse,
    hx_redirect,

    # Return types (the return type is the intent)
    Template,
    InlineTemplate,
    Fragment,
    Page,
    OOB,
    Stream,
    Suspense,
    TemplateStream,
    ValidationError,
    Action,
    FormAction,
    MutationResult,

    # Real-time
    EventStream,
    SSEEvent,

    # Middleware
    Middleware,
    Next,
    AnyResponse,

    # Request-scoped context
    g,
    get_request,

    # Auth
    get_user,
    login,
    logout,
    login_required,
    requires,
    is_safe_url,

    # Forms
    form_from,
    form_or_errors,
    form_values,
    FormBindingError,

    # Errors
    ChirpError,
    ConfigurationError,
    HTTPError,
    MethodNotAllowed,
    NotFound,
    PayloadTooLarge,

    # Markdown
    MarkdownRenderer,
)
```

### Application

:::{list-table}
:header-rows: 1

* - Name
  - Job
* - `App`
  - The application. Mutable during setup, frozen at runtime.
* - `AppConfig`
  - Frozen dataclass of app configuration. See [[docs/about/core-concepts/configuration|Configuration]].
:::

`App` exposes its surface through decorators and methods:

:::{list-table}
:header-rows: 1

* - Decorator / method
  - Job
* - `@app.route(path, methods=..., query_media_types=...)`
  - Register a route handler.
* - `@app.error(code_or_type)`
  - Register an error handler.
* - `@app.template_filter(name=...)`
  - Register a Kida template filter.
* - `@app.template_global(name=...)`
  - Register a Kida template global.
* - `@app.on_startup` / `@app.on_shutdown`
  - Register app lifecycle callbacks.
* - `@app.on_worker_startup` / `@app.on_worker_shutdown`
  - Register per-worker lifecycle callbacks.
* - `@app.tool(name, description)`
  - Register an MCP tool.
* - `app.add_middleware(mw)`
  - Add middleware to the pipeline.
* - `app.run()`
  - Freeze the app and start the development server.
* - `app.check(*, warnings_as_errors=False, coverage=False, deploy=False)`
  - Validate hypermedia contracts (all keyword-only). `deploy=True` runs env-aware rules with production posture.
:::

### HTTP

:::{list-table}
:header-rows: 1

* - Name
  - Job
* - `Request`
  - Frozen dataclass for an incoming request. Properties: `method`, `path`, `query`, `headers`, `cookies`, `content_type`. htmx-awareness: `is_htmx`, `is_narrow_fragment`, `is_boosted`, `is_history_restore`, normalized `htmx_target_id` / `htmx_target_tag`, `htmx_source_id` / `htmx_source_tag`, unified `htmx_trigger`, and `htmx_request_type`. Async body access: `body()`, `text()`, `json()`, `form()`, `stream()`.
* - `Response`
  - HTTP response with a chainable `.with_*()` API (`with_status`, `with_header`, `with_cookie`, `with_hx_redirect`, `with_hx_trigger`, …).
* - `Redirect`
  - 302 redirect convenience: `Redirect(url)`.
* - `FileResponse`
  - Stream a file from disk with the right content type.
* - `JSONResponse`
  - Serialize a value to a JSON response.
* - `hx_redirect`
  - Returns a `Response` with both `Location` and `HX-Redirect` so one handler serves normal and htmx navigation: `hx_redirect(url, status=303, body="", headers=None)`.
:::

:::{warning}
`request.is_fragment` is deprecated — accessing it emits a `DeprecationWarning`
because it is ambiguous for boosted navigations. Prefer returning a `Page(...)`,
which negotiates fragment-vs-full-page for you (the return type is the intent).
When you must branch by hand, use `request.is_htmx` (any htmx request) or
`request.is_narrow_fragment` (a narrow swap, excluding boosted and history
restore).
:::

### Return types

The return type expresses the intent. See the
[[docs/about/core-concepts/return-values|return-type decision tree]] for which to
reach for, and [[docs/build-apps/streaming-updates/html-streaming|Streaming HTML]]
for the three streaming variants.

:::{list-table}
:header-rows: 1

* - Name
  - Job
* - `Template(name, **ctx)`
  - Full template render.
* - `Template.inline(source, **ctx)` / `InlineTemplate(source, **ctx)`
  - Render from a string (prototyping). `Template.inline()` returns an `InlineTemplate`.
* - `Fragment(name, block, **ctx)`
  - Render one named template block.
* - `Page(name, block, **ctx)`
  - Auto-negotiate: fragment for htmx, full page for browsers.
* - `OOB(main, *fragments)`
  - Out-of-band multi-target swap.
* - `Stream(name, **ctx)`
  - Progressive streaming render, no shell-first step.
* - `Suspense(name, *, defer_map={}, defer_blocks=None, **ctx)`
  - Shell-first render; slow blocks stream in as OOB swaps.
* - `TemplateStream(...)`
  - Lower-level streaming response; the template consumes an async iterator.
* - `ValidationError(name, block, **ctx)`
  - 422 response that re-renders a form block with errors.
* - `Action(trigger=...)`
  - 204 no-content action, optional `HX-Trigger`.
* - `FormAction(...)`
  - Fragments for htmx, redirect for plain POST.
* - `MutationResult`
  - Result type for mutation handlers.
:::

### Real-time

:::{list-table}
:header-rows: 1

* - Name
  - Job
* - `EventStream(generator)`
  - Server-Sent Event stream from an async generator.
* - `SSEEvent(data, event, id, retry)`
  - One structured SSE event.
:::

### Middleware and context

:::{list-table}
:header-rows: 1

* - Name
  - Job
* - `Middleware`
  - Protocol for middleware (match the signature; no base class).
* - `Next`
  - The "call the next middleware" callable type.
* - `AnyResponse`
  - Union of everything a handler or middleware may return.
* - `g`
  - Request-scoped mutable namespace (ContextVar-backed).
* - `get_request()`
  - The current request from the ContextVar.
:::

### Auth

See [[docs/build-apps/request-pipeline/builtin|built-in middleware]] for setup
and the secure-by-default stack.

:::{list-table}
:header-rows: 1

* - Name
  - Job
* - `get_user()`
  - The current authenticated user (or `AnonymousUser`).
* - `login(user)`
  - Regenerate the session and set the authenticated user.
* - `logout()`
  - Regenerate the session and clear the user.
* - `@login_required`
  - Require authentication.
* - `@requires(*permissions, policy=None)`
  - Require permissions plus an optional object-level policy callback.
* - `is_safe_url(url)`
  - Whether a redirect URL is safe (relative, same origin).
:::

### Forms

:::{list-table}
:header-rows: 1

* - Name
  - Job
* - `form_from(request, datacls)`
  - Bind form data to a frozen dataclass; raises `FormBindingError` on failure.
* - `form_or_errors(request, datacls, template, block, ...)`
  - Bind, or return a `ValidationError`. Returns `T | ValidationError`.
* - `form_values(form)`
  - Convert a dataclass or mapping to `dict[str, str]` for re-populating a form.
* - `FormBindingError`
  - Raised on bind failure; `.errors` is `dict[str, list[str]]`.
:::

### Errors

The full hierarchy, status codes, and handler patterns live in
[[docs/reference/errors|Errors]].

:::{list-table}
:header-rows: 1

* - Name
  - Job
* - `ChirpError`
  - Base exception for all Chirp errors.
* - `ConfigurationError`
  - Invalid configuration (missing `secret_key`, etc.).
* - `HTTPError`
  - Base for HTTP errors.
* - `NotFound`
  - 404 Not Found.
* - `MethodNotAllowed`
  - 405 Method Not Allowed.
* - `PayloadTooLarge`
  - 413 Payload Too Large.
:::

### Markdown

:::{list-table}
:header-rows: 1

* - Name
  - Job
* - `MarkdownRenderer`
  - Render markdown to HTML (install `chirp[markdown]`).
:::

## Provisional surface

These names work today but may change between minor versions. Most are for
plugin authors, app shells, the reactive system, and the tools/cache layers —
not the everyday request loop.

::::{dropdown} Provisional names (import direct from `chirp`)

:::{list-table}
:header-rows: 1

* - Name
  - Job
* - `CHIRP_CAPABILITIES`
  - Frozenset of capability flags this build guarantees.
* - `CHIRP_DEFER_PENDING_KEY`
  - String key (`__chirp_defer_pending__`) Suspense injects into template context. In templates, prefer `{% if key is deferred %}` — see [[docs/build-apps/streaming-updates/html-streaming|Streaming HTML]].
* - `DEFERRED`
  - Sentinel a Suspense shell uses for an unresolved deferred key.
* - `STOP_POLLING`
  - Response signal that tells htmx polling to stop.
* - `ContractCheck`, `CheckResult`, `ContractIssue`, `ContractCheckSnapshot`, `Severity`
  - Types for writing custom contract checks. See [[docs/quality/contracts-debugging/categories|contract categories]].
* - `ChirpPlugin`
  - Base for packaging reusable setup as a plugin.
* - `HtmxDetails`, `RequestUrlScope`
  - Parsed htmx request metadata and URL scoping helpers on `Request`.
* - `ReactiveBus`, `reactive_stream`, `DependencyIndex`, `ChangeEvent`, `BlockRef`
  - The reactive / signals system. See [[docs/build-apps/streaming-updates/reactive-system|Reactive system]].
* - `ShellAction`, `ShellActions`, `ShellActionZone`, `ShellMenuItem`, `ShellSubmitSurface`
  - App-shell action and menu types. See [[docs/build-apps/ui-extensions/app-shell|App shell]].
* - `ToolDef`, `ToolRegistry`, `ToolEventBus`, `ToolCallEvent`
  - MCP tool registration and event types.
* - `cache_view`, `get_cache`, `DeferredCache`
  - View caching and the deferred-render cache.
* - `use_chirp_ui`
  - Wire the ChirpUI component library into an app. See [[docs/build-apps/ui-extensions/chirp-ui|ChirpUI]].
:::

::::{/dropdown}

## Debug / advanced introspection

Render-pipeline internals for inspecting *how* a request resolved — useful from
middleware or in tests, almost never imported in a handler.

::::{dropdown} Debug names (import direct from `chirp`)

:::{list-table}
:header-rows: 1

* - Name
  - Job
* - `RenderPlan`, `get_render_plan()`
  - Inspect the render decision for a request. See [[docs/build-apps/request-pipeline/render-plan|Render plan]].
* - `SwapResolution`, `resolve_navigation_swap()`
  - How a navigation maps to a swap target.
* - `PageComposition`
  - Explicit page-composition object Chirp builds when layouts are involved. You return a `Page`; Chirp constructs this internally.
* - `RegionUpdate`
  - An OOB region swap descriptor produced during composition.
* - `ViewRef`
  - Internal reference to a resolved view.
:::

::::{/dropdown}

:::{deprecated} not in the public API
`LayoutPage` is **not** a public export — importing `chirp.LayoutPage` emits a
`DeprecationWarning` because it is framework-internal and slated for removal.
Chirp constructs the layout-aware return type for you when a page has a layout;
you return a `Page` or `Template`. Do not import `LayoutPage`.
:::

## CLI

The `chirp` console command (`new`, `dev`, `run`, `check`, `routes`, `freeze`,
`security-check`, `makemigrations`, `migrate`, `shapes-codegen`) is documented in
full, with every flag, in the [[docs/reference/cli|CLI reference]]. `chirp check
<app>` wraps `app.check()`.

## See also

:::{related}
:::
