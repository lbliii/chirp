# Changelog

All notable changes to chirp will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.1] — 2026-03-30

### Added

- **Speculation Rules API** — Auto-generate `<script type="speculationrules">` from route definitions with tiered opt-in via `AppConfig(speculation_rules=...)`: `False`/`"off"` (default), `True`/`"conservative"` (prefetch on hover), `"moderate"` (prefetch eagerly, prerender on hover), `"eager"` (prerender eagerly). XSS-safe JSON escaping in the injected script tag.
- **Invoker Commands validation** — `app.check()` now validates `commandfor` targets and `command` attribute values against the Invoker Commands spec, with negative lookbehind to avoid false positives on `data-command`/`data-commandfor`.
- **htmx 4.0 `<htmx-partial>` alignment** — `HX-Partial` header parsing on `Request`, fragment block resolution for partial requests, and contract validation for `<htmx-partial src="...">` routes.
- **Philosophy doc** — `docs/philosophy.md` coins "hypermedia-native" as Chirp's app style and documents the five core opinions.
- **CLAUDE.md** — Development guide for contributors and AI assistants.

### Changed

- **View Transitions** — Replaced the single boolean toggle with three tiers: `False`/`"off"` (inject nothing, now the default), `True`/`"htmx"` (htmx `globalViewTransitions` only), `"full"` (htmx JS + MPA CSS/meta for cross-document transitions). **Breaking:** default changed from `True` to `False`.
- **README** — Trimmed redundant sections; merged "Hypermedia-Native Python" and "What is Chirp?"; added Zoomies to the Bengal ecosystem table.

### Fixed

- **Suspense** — `format_oob_script` no longer double-nests OOB swap markup.
- **SSE fragment whitespace** — Trailing whitespace stripped from SSE data fields, fixing htmx table row parsing.
- **Markdown filter** — Renderer output is now marked safe to prevent Kida auto-escaping HTML.
- **Standalone examples** — Contacts edit URL reset after save; upload delete route reachable from HTML forms; dashboard/hackernews SSE restored (missing `worker_mode`); ollama chat form clears on submit and shows tools-used label in streaming mode.
- **Kanban template** — Replaced `loop.index` inside `{% call %}` with CSS `:nth-child(odd)` to work with Kida 0.3.0 scope isolation fix.

### Dependencies

- `kida-templates>=0.3.0` (unchanged minimum, but now tested against Kida 0.3.0 scope isolation)
- `bengal-pounce>=0.4.0` (unchanged minimum)

## [0.3.0] — 2026-03-25

### Added

- **Security middleware** — `AllowedHostsMiddleware` validates the `Host` header against a configurable allowlist, rejecting spoofed-host requests. `CSPNonceMiddleware` generates per-request `Content-Security-Policy` nonces accessible via `request.state["csp_nonce"]` and injected into templates.
- **Caching framework** — `chirp.cache` with a `CacheBackend` protocol and three backends: `MemoryCacheBackend`, `NullCacheBackend`, and `RedisCacheBackend`. Includes `CacheMiddleware` for response caching with a configurable key function, `default_cache_key()` / `vary_aware_cache_key()` helpers, and `Vary`-aware keying.
- **Plugin system** — `ChirpPlugin` protocol and `app.mount(prefix, plugin)` for distributing reusable middleware, routes, and template extensions as packages.
- **Schema migrations** — `chirp.data.schema` with introspection, diff, operation generation, and migration file output. `chirp makemigrations` CLI command auto-generates migration files from model changes.
- **Internationalization** — `chirp.i18n` with message catalogs, `LocaleMiddleware` for locale detection, number/date/currency formatting, and `t()` translation helpers wired into templates.
- **CLI** — `chirp makemigrations` and `chirp security-check` subcommands.
- **Vary contract rule** — `contracts.rules_vary` validates that responses include correct `Vary` headers when content depends on request headers.
- **SECURITY.md** — Vulnerability reporting policy.

### Changed

- **htmx headers** — `Request` and `Response` htmx header handling improved for correctness, inspired by django-htmx. `HX-Trigger`, `HX-Push-Url`, `HX-Replace-Url`, and related headers now follow the htmx spec more closely with proper JSON encoding and boolean handling.

### Dependencies

- No dependency changes (all new modules use stdlib or existing deps).

## [0.2.0] — 2026-03-23

### Added

- **Chirp devtools** — Modular debug overlay (inspector, activity, errors, swap highlight) with a split JS bundle under `chirp/server/devtools/`, replacing the monolithic injected debug script path.
- **View Transitions dev tooling** — Development helpers for debugging View Transitions alongside htmx navigation.
- **Browser dev reload** — Optional `AppConfig.dev_browser_reload`: SSE-driven browser refresh when watched files change (pairs with `reload_include` / `reload_dirs`).
- **Render plan snapshots** — Debug snapshot path for render plans (`server/debug/render_plan_snapshot`) for tests and diagnostics.
- **`ShellSubmitSurface`** — Exported type for shell action submit surfaces (`chirp` public API).
- **Shell regions** — Shell region metadata and related shell-action wiring updates.
- **Middleware** — `inject` middleware; layout-debug helpers for development.
- **SSE and logging** — SSE lifecycle and logging improvements aligned with Pounce.
- **Startup and terminal errors** — Clearer formatted messages for startup failures and terminal error output.
- **CLI** — `chirp new` / `chirp run` refinements and scaffold template modules.
- **Examples** — Reorganized into `examples/chirpui/` (chirp-ui apps) and `examples/standalone/` (minimal Chirp); updated `examples/README.md` and per-example docs.
- **Docs** — App shell, UI layers, SSE/streaming guides, layout patterns, and tutorial cross-links.

### Changed

- **Defaults** — `AppConfig.view_transitions` now defaults to `True` (was `False`). Set `view_transitions=False` for API-only apps or tests that require responses without injected View Transition markup/CSS.
- **Defaults** — `AppConfig.log_format` now defaults to `auto` (compact colored lines on a TTY, JSON when piped; aligned with Pounce). Use `CHIRP_LOG_FORMAT` with `auto`, `text`, or `json`.
- **htmx debug** — Wired through the new devtools implementation; large legacy debug script removed from the tree.
- **Contracts and negotiation** — Broader swap/layout/SSE/route-contract checks, template scanning, and content negotiation (including OOB-related paths).
- **Alpine server injection** — Adjustments to Alpine injection and related tests.
- **AI providers** — Internal provider wiring updates.

### Dependencies

- `kida-templates>=0.2.9`
- `bengal-pounce>=0.3.1` (public `PounceError` and related lifespan error exports)
- `chirp-ui>=0.2.1` (optional, for `chirp[ui]`)

## [0.1.9] — 2026-03-12

### Added

- **Route directory contract** — Filesystem routes now have a documented golden path around `_meta.py`, `_context.py`, `_actions.py`, and `_viewmodel.py`, plus section registration via `app.register_section()` for tabs, breadcrumbs, and shell metadata.
- **Route introspection** — Debug builds now expose `X-Chirp-Route-*` headers and a `/__chirp/routes` explorer for inspecting discovered routes, layouts, providers, actions, and route metadata.
- **Synthetic benchmark suite** — New `benchmark` extra, benchmark runners, and benchmark docs compare Chirp against FastAPI and Flask across JSON, CPU, fused sync, and mixed JSON+SSE workloads.

### Changed

- **Sync request path** — Chirp now exposes a fused sync path through `App.handle_sync()` and `SyncRequest`, with lazy query/cookie parsing and pre-encoded content types for simple request-response handlers.
- **Filesystem route ergonomics** — Route metadata, section bindings, shell context assembly, action dispatch, and view-model wiring are now part of the route contract and validated by `app.check()`.
- **CLI scaffolds** — `chirp new` now keeps its templates in dedicated modules, including updated shell and SSE scaffolds.

### Fixed

- **Sync handler execution** — Sync handlers now avoid blocking the event loop on the standard ASGI path while still enabling the faster fused path when a route is eligible.

### Dependencies

- `kida-templates>=0.2.7`
- `bengal-pounce>=0.2.2`
- `chirp-ui>=0.1.6` (optional, for `chirp[ui]`)

## [0.1.8] — 2026-03-10

### Changed

- **Version string** — Now derived from package metadata (single source of truth)

### Dependencies

- `chirp-ui>=0.1.5` (optional, for `chirp[ui]`)

## [0.1.7] — 2026-03-10

### Added

- **App shell guide** — Full documentation for persistent layouts: navigation model (explicit boost on sidebar links), rendering rule (`Page` with `page_block_name`), shell actions, `nav_link` for content links, and interactive shell gotchas (OOB with `hx-swap="none"`, SSE event naming, ContextVar loss, dual template blocks).
- **Islands examples** — `islands/`, `islands_shell/`, `islands_swap/`, and `oob_layout_chain/` examples. Islands inside app shells, islands in dynamically swapped content, and OOB layout chains with depth/nesting.
- **Breadcrumbs and sidebar OOB** — Boosted layout navigation now updates breadcrumbs and sidebar state via OOB swaps.
- **Alpine Focus plugin** — Injected when `alpine=True` for tray/modal overlay focus management. Modals/trays store auto-injected for Alpine apps.
- **Alpine macro improvements** — Dropdown and tabs macros use `x-ref`, `x-id`, focus return, and `$dispatch tab-changed` for better accessibility.
- **Kida integration docs** — Template integration guide and fragments reference.
- **`wizard_form` contract extraction** — Contract checker now extracts IDs from `wizard_form()` macro (fixes false-positive "unknown target" for wizard form containers).

### Changed

- **Shell-owned boost** — `app_shell_layout.html` puts `hx-boost="true"`, `hx-target="#main"`, `hx-swap="innerHTML"`, and `hx-select="#page-content"` on `<main id="main">` (with a `#page-content` wrapper inside). Links inside inherit SPA navigation automatically. Sidebar links (outside `#main`) carry their own attributes via `sidebar_link()`. Also adds `tabindex="-1"` for focus management, scroll-to-top on navigation, `overscroll-behavior: contain`, and a CSS-only loading indicator. `chirpui-transitions.css` scopes View Transitions to `#main` and suppresses VT on `.chirpui-fragment-island`.
- **HX-Reselect removal** — Fragment responses no longer send `HX-Reselect: *`; no longer needed with explicit boost on links.
- **Context provider module names** — `_context.py` files load with path-based names (`_chirp_ctx_collections`, `_chirp_ctx_settings`, etc.) instead of depth-based ones. Sibling directories no longer overwrite each other in `sys.modules`.
- **htmx debug targetError** — "Target Not Found" toast now includes remediation hint: co-locate target with mutating element when target is in a different fragment than the form.

### Fixed

- **Kanban board OOB/SSE** — Move/add/delete routes use empty main fragment so column and stats updates are OOB-wrapped. SSE adds OOB-aware template blocks (e.g. `column_block_oob`, `stats_block_oob`) with correct event naming for `sse-swap` listeners.
- **Wizard form contract** — Templates targeting `wizard_form` IDs no longer get false-positive "unknown target" warnings.

### Dependencies

- `kida-templates>=0.2.6`
- `chirp-ui>=0.1.4` (optional)
- `patitas>=0.3.5` (optional, for markdown)

## [0.1.6] — 2026-03-06

### Added

- **PageComposition API** — Python-first composition with `ViewRef`, `RegionUpdate`, and `PageComposition`. Explicit `fragment_block` / `page_block` semantics and region updates for shell actions. `Page` and `LayoutPage` are normalized through the same render-plan pipeline. See `chirp.templating.composition`.
- **Suspense + layout chain** — Handlers that return `Suspense` from `mount_pages` routes now receive the full layout shell (head, CSS, sidebar). `upgrade_result` wraps `Suspense` in `LayoutSuspense` when a layout chain exists; `render_suspense` wraps the first chunk via `render_with_layouts`. Fragment-only requests skip layout wrapping (same as `LayoutPage`). `layout_context` is merged into template context so cascade values (`shell_actions`, `current_user`) reach Suspense templates.
- **kanban_shell example** — Full example app with app shell, chirp-ui, mount_pages, OOB swaps, SSE, filter sidebar, and CRUD. Demonstrates `mount_pages` + `@app.route` mix.
- **htmx debug overlay** — S-tier debug panel with activity log, inspector, and swap flash when `config.debug=True`. Collapsible framework frames, Kida branding/version, ParseError suggestions.
- **HX-Reselect header** — Fragment responses now send `HX-Reselect: *` so htmx re-parses OOB swaps correctly when the response structure differs from the initial request.
- **Data layout patterns** — chirp-ui guide documents UI layout patterns for app shells and content regions.

### Changed

- **Shell-actions OOB** — Region updates for `#chirp-shell-actions` now use `hx-swap-oob="innerHTML"` instead of `"true"` to preserve container attributes (classes, structure) during boosted navigation.
- **Contracts** — `extract_mutation_target_ids()` uses `\baction\b` in regex to avoid false positives from `form_action`, `data-action`, etc.

### Fixed

- **TemplateNotFoundError** — Shell-actions OOB render catches `TemplateNotFoundError` when chirp-ui is not installed and falls back to empty OOB.

## [0.1.5] — 2026-03-04

### Fixed

- **chirp-ui filters** — `TemplateSyntaxError: Unknown filter 'html_attrs'` when using chirp-ui templates. `use_chirp_ui(app)` now auto-registers chirp-ui filters (`html_attrs`, `bem`, `field_errors`, `validate_variant`). `create_environment` adds env-level fallback when chirp-ui is installed, so filters are present even without explicit `register_filters`. See RFC 001 (component-filter-contract).

## [0.1.4] — 2026-03-04

### Added

- **Enterprise config** — `AppConfig.from_env()` loads config from environment (CHIRP_* vars). Optional `python-dotenv` via `pip install chirp[config]`. New fields: `env`, `redis_url`, `audit_sink`, `feature_flags`, `http_timeout`, `http_retries`, `skip_contract_checks`, `lazy_pages`
- **Health probes** — `chirp.health.liveness()`, `readiness(checks)`, `HealthCheck` for Kubernetes liveness/readiness probes
- **Request ID** — `Request.request_id` for request tracing
- **Structured logging** — `chirp.logging` module for JSON log format and lifecycle events
- **Pluggable session backends** — `SessionStore` protocol with `CookieSessionStore` and `RedisSessionStore`. `RateLimitBackend`, `LockoutBackend` protocols for auth middleware
- **Domain protocol** — `Domain` protocol and `register_domain()` for pluggable feature modules
- **Shell scaffolding** — `chirp new <name> --shell` scaffolds app with persistent shell (topbar + sidebar)
- **Layout slot context** — `LayoutPage` slot content inherits caller context; documented in server
- **form_get example** — New example demonstrating GET-based form search
- **Layout debug middleware** — `LayoutDebugMiddleware` for development
- **Resilience** — `chirp.resilience` with HTTP/DB timeout and retry docs; `Database` gains `connect_timeout`, `connect_retries`

### Changed

- **App architecture** — `app.py` split into `app/` package (compiler, lifecycle, registry, runtime, server, state, diagnostics)
- **Contracts** — `contracts.py` split into `contracts/` package with modular rules (htmx, forms, layout, SSE, islands, swap, etc.)
- **Lazy imports** — Top-level `chirp` uses lazy imports for faster startup
- **Kida errors** — ANSI escape codes stripped from Kida errors in HTTP/SSE/JSON responses
- **Session middleware** — Refactored for pluggable backends

### Fixed

- **Contracts** — Regex for Kida URL extraction in htmx attributes
- **Contracts** — Action+method matrix: GET default, swap safety for form actions

[0.3.1]: https://github.com/lbliii/chirp/releases/tag/v0.3.1
[0.3.0]: https://github.com/lbliii/chirp/releases/tag/v0.3.0
[0.1.8]: https://github.com/lbliii/chirp/releases/tag/v0.1.8
[0.1.9]: https://github.com/lbliii/chirp/releases/tag/v0.1.9
[0.2.0]: https://github.com/lbliii/chirp/releases/tag/v0.2.0
[0.1.7]: https://github.com/lbliii/chirp/releases/tag/v0.1.7
[0.1.6]: https://github.com/lbliii/chirp/releases/tag/v0.1.6
[0.1.5]: https://github.com/lbliii/chirp/releases/tag/v0.1.5
[0.1.4]: https://github.com/lbliii/chirp/releases/tag/v0.1.4

## [0.1.3] — 2026-03-03

(Release notes to be added)

[0.1.3]: https://github.com/lbliii/chirp/releases/tag/v0.1.3

## [0.1.2] — 2026-02-18

### Added

- **Islands (V1)** — Framework-agnostic contract for isolated high-state UI widgets:
  - Mount metadata: `data-island`, `data-island-props`, `data-island-src`, `data-island-version`, `data-island-primitive`
  - `app.check()` validates island mounts and primitive contracts
  - No-build primitive style: plain ES modules from `/static/islands/*.js` without a bundler
  - Runtime diagnostics and safety checks for props, version, and cross-reference
- **chirp-ui integration** — `chirp.ext.chirp_ui.use_chirp_ui(app)` registers chirp-ui static files (CSS, themes).
  Template loader auto-detects chirp-ui when installed. Optional `ui` extra: `pip install bengal-chirp[ui]`
- **Auth hardening** — Production-ready authentication and abuse protection:
  - `AuthRateLimitMiddleware` — Rate limit login/reset endpoints
  - `LoginLockout` — Lockout and backoff for repeated failures
  - `SecurityAudit` — Audit events for failures, lockouts, and blocked attempts
- **Alpine.js support** — `chirp/alpine.html` macros for `x-data`, `x-init`, reactive bindings.
  Server-side Alpine integration and `app.check()` validation for Alpine islands
- **LLM playground example** — New example app demonstrating streaming LLM chat with htmx
- **Documentation** — Guides for islands, auth hardening, Alpine + htmx, and no-build high-state

### Changed

- **Dependencies** — `kida-templates>=0.2.2` (was 0.2.1)
- **CI** — Ruff linting, prek pre-commit, GitHub Actions workflow
- **RAG demo** — Updated with chirp-ui integration

### Fixed

- Various test and type fixes across examples and core modules

[0.1.2]: https://github.com/lbliii/chirp/releases/tag/v0.1.2

## [0.1.1] — 2026-02-15

### Added

- **`chirp` CLI** — New console entry point with three subcommands:
  - `chirp new <name> [--minimal]` — Scaffold a project with app, templates, static assets,
    and tests. `--minimal` generates a single-file starter.
  - `chirp run <app> [--host HOST] [--port PORT]` — Start the dev server from an import
    string (e.g. `chirp run myapp:app`).
  - `chirp check <app>` — Validate hypermedia contracts from the command line.
- **`Template.inline()`** — Prototyping shortcut that renders a template from a string
  instead of a file. Returns an `InlineTemplate` instance that works through content
  negotiation without requiring a `template_dir`.
- **`InlineTemplate`** — New return type for string-based template rendering. Separate
  from `Template` so negotiation can distinguish it and `app.check()` can warn about
  inline templates in production routes.
- **Built-in template filters** — `field_errors` extracts validation messages for a single
  form field from an errors dict. `qs` builds URL query strings, automatically omitting
  falsy values. Both are auto-registered in the Kida environment at startup.
- **`form_or_errors()`** — Glue function that combines `form_from()` and `ValidationError`
  into a single call. Returns `T | ValidationError`, eliminating the try/except boilerplate
  for form binding errors.
- **`form_values()`** — Utility that converts a dataclass or mapping to `dict[str, str]` for
  template re-population when validation fails.
- **Form field macros** — Shipped in `chirp/forms.html`, importable via
  `{% from "chirp/forms.html" import text_field %}`. Five macros (`text_field`,
  `textarea_field`, `select_field`, `checkbox_field`, `hidden_field`) render labelled
  fields with inline error display using the `field_errors` filter.
- **Filesystem-based page routing** — Layout-nested page discovery from directory structure.
- **`app.provide()`** — Dependency injection for request-scoped context providers.
- **Reactive block pipeline** — Structured reactive templates with derived state.
- **SSE safety checks** — Contract validation for event streams and event cross-reference.
- **Safe target** — `hx-target` safety for event-driven htmx elements.
- **Security headers middleware** — HSTS, X-Content-Type-Options, etc.
- **View transitions** — OOB swap support for View Transitions API.
- **Production deployment** — Pounce Phase 5 & 6 support, deployment documentation.
- **Typed extraction** — Query/form/JSON extraction via dataclasses in handler signatures.

### Dependencies

- `kida-templates>=0.2.1` — Template engine
- `bengal-pounce>=0.2.0` — ASGI server

[0.1.1]: https://github.com/lbliii/chirp/releases/tag/v0.1.1

## [0.1.0] — 2026-02-09

Initial release of Chirp — a Python web framework for HTML-over-the-wire apps,
built for Python 3.14t with free-threading support.

### Added

#### Core Framework

- `App` — ASGI application with route registration, middleware pipeline, and
  lifecycle management
- `AppConfig` — Frozen configuration with sensible defaults
- Type-driven content negotiation: return strings, dicts, `Template`, `Fragment`,
  `Stream`, `EventStream`, `Response`, or `Redirect` from route handlers

#### Routing

- Decorator-based route registration with `@app.route(path)`
- Path parameters with type conversion (`/users/{id:int}`)
- Method dispatch (`GET`, `POST`, `PUT`, `DELETE`, etc.)
- Automatic `HEAD` and `OPTIONS` handling

#### Templates (Kida Integration)

- `Template(name, **ctx)` — Full-page Kida template rendering
- `Fragment(name, block, **ctx)` — Render named template blocks independently
  for htmx partial updates
- `Stream(name, **ctx)` — Progressive HTML streaming via Kida
- Auto-discovery of template directories

#### Real-Time

- `EventStream(generator)` — Server-Sent Events for real-time HTML updates
- SSE with Kida-rendered fragments for zero-JS real-time UI

#### HTTP

- Immutable `Request` with query params, headers, cookies, body parsing
- Chainable `Response` with `with_header()`, `with_cookie()` methods
- `Redirect` for HTTP redirects
- `form_from()` for typed form binding and validation

#### Middleware

- Protocol-based middleware (`async def mw(request, next) -> Response`)
- Built-in: CORS, StaticFiles, HTMLInject, Sessions
- `app.add_middleware()` for composable request/response pipelines

#### Security

- Session middleware with signed cookies (via itsdangerous)
- `login()`, `logout()`, `get_user()` authentication helpers
- `@login_required` and `@requires()` authorization decorators
- `is_safe_url()` for open redirect protection

#### Data

- `Database` — Typed async database access (SQLite via aiosqlite, PostgreSQL
  via asyncpg)

#### AI

- `LLM` — Provider-agnostic LLM streaming via raw HTTP
- `ToolCallEvent` for structured tool calling

#### Testing

- `TestClient` — HTTPX-based test client for isolated route testing

#### Developer Experience

- `app.run()` — Built-in development server via Pounce
- `app.check()` — Compile-time validation of the full hypermedia surface
  (routes, template refs, fragment blocks)
- `py.typed` PEP 561 marker for type checker support
- Free-threading declaration (`_Py_mod_gil = 0`)

### Dependencies

- `kida-templates>=0.1.2` — Template engine
- `anyio>=4.0` — Async runtime
- `bengal-pounce>=0.1.0` — ASGI server

[0.1.0]: https://github.com/lbliii/chirp/releases/tag/v0.1.0
