# Changelog

All notable changes to chirp will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.7.1] — 2026-05-30

### Changed

- **DevTools** — Chirp DevTools now uses native debug runtime wiring and server-owned EventStream traces instead of replacing browser `EventSource`.

    Internal debug/reload routes are classified as framework-owned, hidden from normal DevTools activity by default, and protected from application route collisions at freeze time. Debug responses also include typed return traces so DevTools can report the negotiated `Template`, `Fragment`, `PageComposition`, `OOB`, `Suspense`, `Stream`, `EventStream`, `Action`, or `ValidationError` branch without parsing response bodies.

### Fixed

- `_actions.py` dispatch now passes the current `Request` into action functions and request-aware `app.provide()` factories, preserving request-scoped service context for filesystem actions.

## [0.7.0] — 2026-05-14

### Added

- **Benchmarks** — added a networked template-rendering workload to the Chirp, FastAPI, and Flask comparison runner.
- **Fragment safety** — `app.check()` now warns when a fragment block depends on imports or bindings declared only inside an ancestor block, and `chirp.testing` adds `RouteSmokeCase` / `assert_route_smoke` for full-page and fragment route smoke checks.
- **Request URL scope** — `RequestUrlScope`, `request.with_url_scope(...)`, `request.scoped_url(path)`, and `request.url_for(...)` let middleware generate tenant/base-path public URLs without changing `app.url_for(...)` or rewriting rendered HTML.
- **`csrf_form` contract check** — when `CSRFMiddleware` is active, `app.check()` now warns on static mutating forms that do not render `csrf_field()`, call `csrf_token()`, or include an `_csrf_token` field.
- Added drift guards that keep `docs/public-api.md` aligned with `_API_STATUS`, require every `AppConfig` field to appear in the configuration guide, and require changelog fragments for branch changes to the top-level public API registry.
- Added provisional `DeferredCache` for explicit server-side reuse of Suspense deferred values, including TTL expiry and same-key in-flight deduplication.
- Benchmark comparison runner now covers SQLite DB workloads and Starlette/Litestar targets, with report headers that record Python version and GIL/free-threaded mode for 3.14 vs 3.14t comparisons.
- Document the 2026-05-03 release-readiness gate run, mark completed/stale planning docs with current status, complete the initial 1.0 public surface, `AppConfig`, and stable error-message audits, correct the configuration guide, promote `JSONResponse` to stable, and make selected routing/forms/session errors more actionable.
- Reactive apps can now expose `reactive_index`, `reactive_emitted_paths`, `reactive_audience_scopes`, and `reactive_connection_scopes` through `app.set_contract_check_data()` so `app.check()` can warn about emitted paths missing from the `DependencyIndex` and audience-filtered scopes that lack `ConnectionInfo` subscribers.

### Changed

- **Pounce 0.7 operator guidance** — documented the `bengal-pounce>=0.7.0` production boundary, paired `chirp check` with `pounce check`, described Pounce config inspection commands, clarified that `pounce.toml` is Pounce-native today while `app.run()` and `chirp run` use `AppConfig`, and deferred trusted proxy, compression, and introspection `AppConfig` fields pending a separate security-facing API decision.
- **Scoped auth redirects** — `@login_required` and `@requires` now preserve `RequestUrlScope` in generated `?next=` login redirects, so tenant/base-path middleware keeps users on the public URL after login.
- Raised Chirp's optional `ui` extra, development example dependency, and new scaffolded project floor to `chirp-ui>=0.9.0`.
- Require `kida-templates>=0.9.0`, preserve Chirp's missing-block `KeyError` behavior when Kida reports missing blocks with its typed runtime error, and surface Kida 0.9 component-call, dotted context-contract, literal-attribute, escape-audit, and privacy-lint diagnostics through `app.check()`.
- `EventStream` now matches the documented htmx SSE default for yielded `Fragment` values: fragments without an explicit target emit on the `message` channel, while targeted fragments still use their target as the event name. The `sse_scope()` macro and bundled examples now listen on `message` by default, and the SSE cross-reference contract can infer literal `SSEEvent(event=...)` and `Fragment(target=...)` yields from route source.

### Fixed

- Aligned `url_for()` and contract route matching with typed route converters. `url_for()` now rejects path values that do not match the route converter, and `app.check()` no longer treats literal URLs like `/users/alice` as valid matches for `/users/{id:int}`.
- Fixed lifespan startup cleanup so a database connection opened during startup is disconnected when a later startup hook or migration step fails before `lifespan.startup.complete`.
- Fixed router parameter matching so typed and string parameter routes at the same path depth no longer shadow each other or reuse the wrong parameter name. Route parsing now rejects malformed parameter segments, unknown converters, non-final `{name:path}` converters, and duplicate route shapes that differ only by parameter name.
- SQLite migrations now wrap the migration SQL and tracking-table insert in one explicit transaction, so a failed multi-statement migration does not leave partially-created tables or a stale migration record.
- `CacheMiddleware` now preserves cached response headers and content type on cache hits instead of reconstructing every cached response as bare `text/html`.
- `app.check()` now reports `fragment_target_scan` errors when a page template cannot be inspected during fragment target orphan checks, instead of silently skipping that template and potentially hiding stale or misspelled target registrations.
- `chirp security-check` now matches `app.check()` host validation by allowing wildcard `allowed_hosts` in development while still failing wildcard hosts outside development.
- Debug browser reload now boots idempotently, skips htmx swaps, honors `reload_include=()` as an opt-out, and no longer passes browser asset suffixes to Pounce as process-reload extensions.

### Security

- **Middleware security defaults** — auth rate limiting now uses the socket client address by default instead of trusting `X-Forwarded-For`, credentialed wildcard CORS is rejected, and `app.check()` flags wildcard `allowed_hosts` outside development.

    **Migration** — Apps behind a trusted proxy that intentionally key auth rate limits by `X-Forwarded-For` must pass `AuthRateLimitConfig(key_header="x-forwarded-for")`; credentialed CORS must list explicit origins.
- **SSE and markdown trust boundaries** — `SSEEvent` now rejects event names and IDs containing CR, LF, or NUL characters, rejects negative retry values, and normalizes carriage returns in data frames. `MarkdownRenderer` and `register_markdown_filter()` now sanitize unsafe HTML, event attributes, and unsafe link/image URLs by default.

    **Migration** — Trusted markdown that intentionally preserves raw HTML can pass `sanitize=False`. Apps constructing `SSEEvent(event=...)` or `SSEEvent(id=...)` must pass single-line field values.
- `CacheMiddleware` now bypasses cache reads and writes for GET requests carrying `Cookie` or `Authorization` headers, preventing default site-wide caching from replaying authenticated or session-specific HTML.
- `chirp freeze` now rejects expanded URLs containing `.` or `..` path segments before mapping them to output files. Unsafe `freeze_params` values are reported in `FreezeResult.errors` and are not written outside the target output directory.

## [0.6.0] — 2026-05-02

### Added

- **DevTools Swap Doctor** — expanded htmx activity rows now explain swap behavior with effective `hx-*` inheritance, selector-match checks, target presence, render intent, render-plan context, broad-target warnings, full-document fragment smells, and no-op swap detection. Request records are correlated by XHR when available so overlapping htmx requests keep their diagnostics attached to the right row. New scaffolded apps include `AGENTS.md` guidance for activating DevTools, and browser-capable agents can discover the diagnostics API with `window.ChirpHtmxDebug.help()`.
- **Hero-app enablers** — added `Page.mounted(...)`, top-level `JSONResponse`, repeated `form_from()` list binding, contract coverage counters, and stricter testing helpers for full-page/fragment/id assertions.
- **Named routes and `url_for`** — Routes mounted via `app.mount_pages()` now carry a default dotted name (`/contacts/{contact_id}` → `"contacts.contact_id"`, `/` → `"index"`). Override per-page by setting `name = "…"` at module level in `page.py`. Reverse names to URLs with `app.url_for("contacts.contact_id", contact_id=42)` or the matching `{{ url_for(...) }}` template global (registered via `setdefault`, so user overrides still win). Path params are percent-encoded; remaining kwargs become a urlencoded query string; `None` values are dropped. A new `route_names` contract check fails `app.check()` when two routes at *different* paths claim the same name (method variants at the same path are not collisions).
- **`app.mount_app(prefix, sub_app)`** — hoist a pre-freeze Chirp `App` into a parent app at a URL prefix. Sub-app's pending routes are path-prefixed, middleware / hooks / loaders / contract checks are appended, and template globals / filters / providers / error handlers / severity overrides merge with parent-wins semantics (dropped entries surface as INFO issues in a new `mount_app_merge` contract category). Sub-app is **consumed** — `sub_app.freeze()` / `sub_app.run()` raise `RuntimeError` after the mount, so you can't accidentally serve a half-mounted standalone runtime. Designed for transitional migrations where two full apps need to share one port; see `docs/routing/mounting.md` and `docs/rfcs/005-mount-app.md` for merge rules and unsupported sub-app state.
- **`chirp check --coverage`** — show contract coverage counters for POST form contracts, mounted page contracts, app-shell targets, and OOB regions.
- **`examples/chirpui/forum_shell`** — added a compact forum/PBP reference app showing mounted pages, app-shell OOB state, typed reply forms with repeated mention fields, and a JSON mention-search endpoint.
- **`page_handlers` contract check** — `app.check()` now fails fast at startup when a `page.py` defines no recognised HTTP method handler (`get`/`post`/… or `handler`), instead of letting requests hit a 404/500 at runtime. Handler-shaped typos (`def handle`, `def GET`, `def index`) emit a WARNING; a fully missing handler emits an ERROR. Tune via `app.override_contract_severity("page_handlers", …)`.
- Add an in-process Chirp core benchmark suite for template, fragment, OOB, Suspense, SSE fanout, and filesystem route dispatch workloads with reproducible JSON output.
- Document the top-level public API stability tiers and add tests that snapshot exported names and require every export to have a stability classification.
- Grouped `app.check()` terminal output by contract concern and included total elapsed time in contract check reports.
- Replaced the legacy roadmap narrative with an executable maturity roadmap for 0.5.x reliability, contracts, performance, API discipline, and the PBP forum proof app.

### Changed

- **In-repo examples migrated to `url_for`** — every chirpui and standalone example now reverses URLs through `app.url_for` / `{{ url_for(...) }}` instead of hardcoded `hx-get`/`hx-post`/… strings. `rg 'hx-(get|post|put|delete|patch)="/' examples/` drops from 88 hits to 3 (the remaining hits are an intentional 404 sentinel URL and two test assertions verifying rendered HTML). Route names follow the RFC 003 dotted-path convention for `@app.route(...)` handlers (`index`, `tasks.add`, `tasks.move`, etc.).
- **Railway env config** — `AppConfig.from_env()` now falls back to Railway's `PORT`, binds to `0.0.0.0` when a Railway environment is detected, and includes `RAILWAY_PUBLIC_DOMAIN` plus `healthcheck.railway.app` in `allowed_hosts` when `CHIRP_ALLOWED_HOSTS` is not set.
- **`Page(...)` TypeError ergonomics** — Calling `Page("page.html", **ctx)` without a block name now raises a `TypeError` that points at `Template("page.html", **ctx)` (the correct type for full-page renders without htmx negotiation) and references the return-values decision tree. Users reaching for `Page` when they mean `Template` no longer get a generic "missing positional argument" traceback.
- Raised Chirp's `chirp-ui` dependency floor to `>=0.6.0` for the optional `ui` extra, development example tests, and newly scaffolded projects. `use_chirp_ui(app)` now injects ChirpUI's packaged `themes/app-theme-starter.css` after `chirpui.css` so the theme toggle has light/dark/system tokens by default, and new scaffolds load app-owned `static/theme.css` as the override slot. Chirp now surfaces ChirpUI 0.6 manifest/runtime metadata in `app.check()`, emits an informational `chirpui_runtime` issue when app templates import ChirpUI without `use_chirp_ui(app)`, and updates the mounted-pages shell example to use `nav_tree(branch_mode="linked")`.
- Raised Chirp's docs build dependency floor to `bengal>=0.3.2` so non-workspace documentation builds pick up the latest Bengal production-build fixes.

### Fixed

- **Cache keys** — default cache keys now include the query string and htmx response shape so paginated forum views, full-page responses, boosted responses, and local fragments do not collide under `CacheMiddleware`.
- **Form contracts** — block-scoped `FormContract` validation now respects nested template blocks and Kida control tags instead of truncating at the first nested `{% endblock %}`.
- **Kida 0.8** — bump the minimum `kida-templates` version to `>=0.8.0` and resolve relative template references (`./`, `../`) plus configured `@alias/` prefixes before dead-template and inherited swap-safety analysis.
- **Shell outlets** — boosted navigation into an app-shell outlet now keeps responses selectable by inherited `hx-select` contracts, with `chirpui/app_shell_layout.html` layouts using the registered `chirpui-app-shell` preset automatically and `app.check()` warning when a broad `hx-target`/`hx-select` shell is missing `{# outlet: ... #}` metadata.
- Fixed example drift against current Kida and Chirp contracts, including Hacker News nested macros, Kanban anonymous-user rendering, Survey default form values, and Kanban startup contract errors.
- Made `ReactiveBus.emit_sync()` and `ReactiveBus.close()` hand off cross-thread queue delivery to each subscriber's owning event loop instead of mutating `asyncio.Queue` from arbitrary threads.
- Make `ToolEventBus`, the PostgreSQL LISTEN helper, and the standalone chat example hand cross-thread event delivery back to each subscriber's owning event loop.

## [0.5.0] — 2026-04-23

### Added

- **Alpine on streaming HTML** — `AlpineInject` rewrites `StreamingResponse` bodies (e.g. `Suspense`) to insert the Alpine bundle before `</body>`, with the same deduplication as buffered pages.
- **Ancestor block pruning** — `_find_deferred_blocks` now drops blocks whose `depends_on` is a strict superset of another matched block, preventing large parent blocks (e.g. `page_content`) from being re-rendered as wasted OOB chunks.
- **Concurrency stress tests** — 25 new tests covering all Lock-protected modules (bus, cache, rate-limiter, lockout, OOB registry), ContextVar isolation, and database pool stress.
- **Configurable queue depth** — `ReactiveBus(maxsize=N)` controls per-subscriber queue size (default 256, unchanged).
- **Contract checks — source-level SSE event inference** — ``check_sse_event_crossref`` now AST-walks each ``@contract(returns=SSEContract(...))`` handler for literal ``SSEEvent(event="...")`` and ``Fragment(target="...")`` yields. A ``sse-swap="X"`` on a child of ``sse-connect`` that matches neither the declared ``event_types`` nor any inferred literal is promoted from ``WARNING`` to ``ERROR`` at startup — the silent-mismatch class of bug (htmx drops unmatched events) now fails loud. Handlers with non-literal ``event=`` / ``target=`` (variable, f-string, or function call) disable inference for that route; an ``INFO`` issue is emitted so operators can annotate ``SSEContract.event_types`` to restore fail-loud coverage.
- **Form action contract** — `chirp check` reports `<form action="/path" method="post">` targets that lack a `FormContract` declaration.
- **Layout `HX-Target` + outlet** — `LayoutChain.find_start_index_for_target` matches `{# outlet: element_id #}` as well as `{# target: #}`, so boosted `HX-Target: #main` resolves for chirp-ui app shells (`{# target: body #}` + `{# outlet: main #}`).
- **Layouts, Alpine, & Reactive docs** — Filesystem routing (outlet + `main`), route contract reference, streaming HTML + Suspense + Alpine, built-in middleware, ReactiveBus API, DependencyIndex, derived paths, observability counters, thread safety stress test coverage, contract checks (reactive_block, reactive_cycle, oob_target, form_action), SSE monitoring, and shell tabs.
- **Native fragment blocks — ``{% fragment name %}...{% end %}``** — Chirp now recognises kida 0.6.0+'s native fragment directive as a swap-only target: the block body is suppressed during a full-template render (``Template("p.html", ...)``) and only emits content when addressed by ``Fragment("p.html", "name", ...)``, the ``/_frag{path}?_b=name`` dispatcher, or a ``{% fragment %}`` target in a ``PageShellContract``. Use this instead of the ``{% block %}`` + ``{% if foo is defined %}`` workaround for blocks that should never render inline — e.g. success panels, SSE payloads, OOB swap targets.

  **Contract rules updated to match** — ``check_unreachable_blocks`` no longer flags ``fragment=True`` blocks as unreachable from composition roots: they are unreachable *by design*. Every other rule (``check_fragment_target_orphans``, ``check_page_shell_contracts``, ``rules_sse`` cross-reference) walks ``block_metadata()`` and already treats fragment and regular blocks identically.
- **OOB target contract** — `chirp check` warns when `hx-swap-oob` elements reference IDs not found in any template.
- **Reactive contract rules** — `chirp check` validates that `DependencyIndex` block references point to real template blocks and that derivation graphs are acyclic.
- **ReactiveBus observability** — `emitted_count`, `dropped_count`, and `subscriber_count` properties for monitoring event throughput and back-pressure.
- **Suspense templates docs** — Document `{% if key is not none %}` / `__chirp_defer_pending__` instead of bare `{% if key %}` (falsy empty results look like perpetual skeletons). Updated `return-values.md`, streaming guide, `CLAUDE.md`, and API reference.
- **`Suspense.defer_blocks`** — optional explicit list of blocks to re-render as OOB chunks, bypassing `block_metadata()` static analysis. Use when deferred values are passed through macro arguments that the analyzer can't trace.
- **`__chirp_defer_pending__` / `CHIRP_DEFER_PENDING_KEY`** — Suspense shell renders (and sync-only Suspense renders) inject a `frozenset` of context key names still awaiting resolution; deferred block re-renders use an empty frozenset. Templates can branch on membership instead of overloading `None` / truthiness.
- **`alpine_json_config` docs** — Chirp `CLAUDE.md`, Alpine guide, and built-in middleware reference document the template global and its relationship to `AlpineInject`.
- **`alpine_json_config` template global** — when `alpine=True`, templates can emit `<script type="application/json">` tags with safely escaped ids and JSON for Alpine components (`alpine_json_config("my-id", data)`).
- **`chirp.errors.BlockNotFoundError`** — Multi-inherits from `ChirpError` and `KeyError`, so existing `except KeyError` handlers (including Kida's documented `render_block` contract) continue to catch it. Carries `template`, `block`, and `region` attributes for structured error handling.
- **`register_oob_region(..., optional=True)`** — Opt-out for shell regions that legitimately appear in only some layouts. Optional orphans stay at `WARNING`; at render time, optional regions missing from the current layout are silently dropped (not emitted as empty OOB wrappers). `chirp.ext.chirp_ui`'s auto-registered breadcrumb, sidebar, title, and shell-actions regions all default to `optional=True`.

### Changed

- **Breaking — SSE event-name default** — ``EventStream`` now emits yielded ``Fragment`` payloads as **unnamed** SSE frames (matching htmx's default ``message`` event name). Previously the wire frame defaulted to ``event: fragment``, requiring every consumer to declare ``sse-swap="fragment"`` — a chirp-specific quirk that silently broke stock htmx-sse snippets.

  **Migration** — In templates, change ``sse-swap="fragment"`` to ``sse-swap="message"`` (htmx-sse requires the attribute to be present to wire up the listener; ``"message"`` is the default event name emitted by untargeted ``Fragment`` yields). The ``chirp/sse.html`` macro now defaults to ``swap="message"``; pass ``sse_scope("/events", swap="status")`` to opt into a named channel. To keep the old wire shape explicitly, yield ``SSEEvent(data=rendered_fragment, event="fragment")`` instead of a bare ``Fragment``, or pass ``target="fragment"`` on the Fragment.
- **Chirp-ui integration** — Suppress ``UserWarning`` when optional chirp-ui implementations replace Chirp’s built-in filter stubs (detected via ``__module__`` prefix).

  **Contract checks** — ``Template``/``Page``/``Suspense``/``Fragment`` reference scan includes ``Page`` and ``Suspense`` paths; filesystem routes expose the original handler as ``Route.page_source_handler`` so dead-template and fragment checks see user source inside the async page wrapper. Import ``make_route_link_attrs`` via ``importlib`` when wiring ``route_link_attrs`` for ty-friendly optional installs.

  **Context cascade** — Deduplicate identical override notices; omit INFO when child providers intentionally override ``shell_actions``, ``shell_mode``, or ``Components``.
- **Dependencies** — `kida-templates>=0.6.0` (bumped from `>=0.3.0`), `bengal-pounce>=0.6.0` (bumped from `>=0.4.0`).
- **Scaffold template** — `chirp new` now pins `bengal-chirp>=0.2.0` (was `>=0.1.9`). Existing projects are unaffected; new projects get the latest contract fixes and Alpine injection improvements from 0.2.x.
- **OOB render errors fail loud** — `execute_render_plan` previously caught every exception raised while rendering an OOB region and substituted `html = ""`, producing empty swaps that wiped existing DOM content. Missing blocks now raise `chirp.errors.BlockNotFoundError`; genuine render errors (context `KeyError`, filter errors) propagate to the route error handler. See `docs/guides/oob-registry.md`.
- **Orphan OOB registrations error at freeze** — `app.check()` now emits `Severity.ERROR` (was `WARNING`) when the OOB registry contains a block no layout template defines. Non-optional orphans block debug-mode freeze; `app.override_contract_severity("oob_registry", Severity.WARNING)` restores prior behavior globally. Add `optional=True` to `register_oob_region()` calls for regions that legitimately appear in only some layouts.
- **`AppConfig.strict_undefined` — `True` by default** — chirp now passes `strict_undefined` through to kida's `Environment`, matching kida 0.7.0's new default. Templates referencing a missing attribute/key raise `UndefinedError` instead of silently rendering empty. Opt out with `AppConfig(strict_undefined=False)` during migration; fix callsites with `obj.attr ?? ""`, `| default(...)`, or `{% if obj.attr is defined %}`.
- **chirp-ui floor bumped to `>=0.5.0`, kida-templates to `>=0.7.0`** — picks up chirp-ui 0.5 (agent-grounding manifest, composite contract tests, `@layer chirpui.*` cascade public API, `set_strict("auto")` + `CHIRP_UI_DEV`), kida 0.7 (`strict_undefined=True` default, Jinja2 parser hints), and chirp-ui 0.4 sharp-edges audit. `use_chirp_ui(app, strict="auto")` now delegates to the `CHIRP_UI_DEV` env var so dev hosts opt in once without code changes. Per-request `_ChirpUIStrictMiddleware` retired — chirp-ui strict mode is now set once at `use_chirp_ui()` registration.
- Remove 49 no-op `from __future__ import annotations` imports (PEP 649 default on 3.14), add 11 TypedDicts for stable dict shapes in tools/debug modules, and convert 3 dispatch chains to `match/case`.

### Fixed

- **Route contract** — `chirp check` no longer reports missing `_meta.py` for routes whose `_meta.py` defines only `meta()` (dynamic metadata). Those routes register a meta provider at discovery time; the checker now treats that as satisfying the route metadata contract.

## [0.3.3] — 2026-03-30

### Fixed

- **CSP defaults** — `SecurityHeadersMiddleware` and `CSPNonceMiddleware` now allow `unpkg.com` (htmx), `cdn.jsdelivr.net` (Alpine.js), and inline scripts in the default `script-src`, fixing silent breakage of htmx/JS actions.

### Dependencies

- `chirp-ui>=0.2.3` (bumped from `>=0.2.2`)

## [0.3.2] — 2026-03-30

### Dependencies

- `chirp-ui>=0.2.2` (bumped from `>=0.2.1`)

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

[0.3.3]: https://github.com/lbliii/chirp/releases/tag/v0.3.3
[0.3.2]: https://github.com/lbliii/chirp/releases/tag/v0.3.2
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
