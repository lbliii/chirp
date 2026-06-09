---
title: Contract Category Reference
description: app.check categories, default severity, fix targets, and severity override examples
draft: false
weight: 35
lang: en
type: doc
tags: [contracts, app-check, diagnostics, reference]
keywords: [contract categories, app.check, chirp check, severity, warnings-as-errors]
category: reference
---

`app.check()` reports each issue with a category. Treat the category as the
stable handle for CI policy and the message as the concrete fix target. Good
messages name the route, template, block, selector, registration, config flag,
middleware, import string, or contract data that needs to change.

`chirp check myapp:app --warnings-as-errors` promotes warnings at the CLI
boundary. For app-specific policy, override a category before running checks:

```python
from chirp.contracts.types import Severity

app.override_contract_severity("dead", Severity.WARNING)
app.override_contract_severity("page_handlers", Severity.WARNING)
```

Overrides are deliberately category-scoped. Do not demote fail-loud categories
such as missing required OOB regions or broken SSE listeners unless you have a
temporary migration plan and a narrower test that covers the user-visible path.

## Routing And Pages

| Category | Default severity | Fix target |
|---|---|---|
| `routing` | ERROR | Replace Flask-style route params such as `<id>` with Chirp's `{id}` route syntax. |
| `route_names` | ERROR | Rename one route or set an explicit module-level route name so `app.url_for()` is unambiguous. |
| `route_contract` | ERROR / INFO / WARNING | Align filesystem route files, metadata, and declared contracts with discovered routes. |
| `page_handlers` | ERROR / WARNING | Add a recognized `page.py` handler (`get`, `post`, another HTTP method, or `handler`) and fix handler-shaped typos. |
| `method` | ERROR | Ensure handlers are callable and route methods are supported. |
| `target` | ERROR | Fix route target declarations that point at missing routes. |
| `page_context` | WARNING | Move page block dependencies into the context available to direct fragment renders. |
| `page_shell` | ERROR | Register or correct app-shell targets, outlets, and shell contracts used by filesystem pages. |
| `layout_chain` | INFO / WARNING | Fix duplicate layout targets, default inner `body` targets, broad `hx-disinherit`, or inheritance inside composed layouts. |
| `layout_outlet` | WARNING | Declare and register the outlet used by boosted navigation so narrow htmx responses are selected correctly. |
| `layout_frame` | WARNING | Keep immutable frame targets out of the fragment-target registry. |
| `context_cascade` | INFO / WARNING | Fix `_context.py` signatures, inherited context providers, and intentional child overrides. |
| `mount_app_merge` | INFO | Review parent-wins dropped entries from `mount_app()` such as globals, filters, providers, handlers, and severity overrides. |
| `setup` | ERROR | Fix checker setup problems such as missing template loaders before trusting downstream contract output. |

## Templates And Blocks

| Category | Default severity | Fix target |
|---|---|---|
| `dead` | WARNING | Remove unused templates or add a route, include, import, layout, or explicit docs/tool reference. |
| `orphan` | INFO | Reference the route from a template, mark it explicitly referenced, or accept that static analysis cannot see dynamic navigation. |
| `fragment` | ERROR | Fix `FragmentContract` declarations that point at missing templates or blocks. |
| `fragment_scope` | WARNING | Move imports or bindings into the fragment block when direct block rendering would skip ancestor scope. |
| `fragment_target_orphan` | ERROR / WARNING | Register the missing block for a required fragment target, or mark legitimately absent regions optional. |
| `fragment_target_scan` | ERROR | Fix the template parse/load error that prevented fragment target orphan checks from completing. |
| `unreachable_block` | WARNING | Move sibling page blocks under the rendered page root or make them real fragment targets. |
| `composition_extends` | WARNING | Stop extending layout templates from page templates; compose pages into layout content blocks instead. |
| `htmx_partial` | ERROR | Correct `<htmx-partial>` sources, blocks, and route references. |
| `inline_template` | WARNING | Replace inline template strings when a named template would be checkable and reusable. |
| `boundary` | INFO | Keep route, template, and extension boundaries aligned so checks can map diagnostics to the right source. |
| `islands` | ERROR / WARNING | Register island roots and targets consistently when island strictness is enabled. |
| `component` | ERROR | Fix Kida/chirp-ui component-call diagnostics; precision depends on available typed component metadata. |
| `template_contract` | WARNING | Replace legacy component action contracts with current declarations. |
| `template_context` | ERROR / WARNING | Add missing dotted context paths to the provided or optional contract data, or stop reading them. |
| `template_escape` | WARNING | Review trusted-markup or escaping diagnostics surfaced by Kida. |
| `template_privacy` | WARNING | Remove private literals or mark non-public template content appropriately. |
| `i18n_missing_key` | WARNING | Add the `t("…")` key to the locale JSON catalog(s) under the i18n directory, or remove the `t()` call. |

## HTMX And Swaps

| Category | Default severity | Fix target |
|---|---|---|
| `hx-target` | WARNING | Fix static `hx-target="#id"` selectors that do not match any known template ID. |
| `hx-indicator` | WARNING | Fix static `hx-indicator="#id"` selectors that do not match any known template ID. |
| `hx-boost` | WARNING | Use only `hx-boost="true"` or `hx-boost="false"` for static boost values. |
| `selector_syntax` | ERROR | Fix invalid selector syntax in static htmx selector-bearing attributes. |
| `select_inheritance` | WARNING | Add explicit `hx-select`, `hx-select="unset"`, or `hx-disinherit` where broad inherited selectors can empty swaps. |
| `swap_safety` | INFO / WARNING | Add explicit local targets or isolate SSE swaps from broad inherited `hx-target`/`hx-swap`. |
| `fragment_island` | INFO | Add `hx-disinherit` or a fragment-island wrapper around local mutation targets. |
| `view_transition_scope` | WARNING | Scope View Transitions to navigation-only elements, not broad OOB/SSE live-update containers. |
| `oob_registry` | ERROR / WARNING | Add the registered OOB block/target, fix a typo, or make the region optional only when absence is legitimate. |
| `oob_target` | WARNING | Fix `hx-swap-oob` IDs that do not appear in any known template. |

## SSE And Reactive

| Category | Default severity | Fix target |
|---|---|---|
| `sse` | ERROR | Fix route-level `SSEContract` declarations that point at missing or inconsistent event/template data. |
| `sse_self_swap` | ERROR | Move `sse-swap` from the `sse-connect` element to a child sink. |
| `sse_scope` | ERROR | Add an SSE scope boundary such as `hx-disinherit="hx-target hx-swap"` when streams live inside broad htmx targets. |
| `sse_crossref` | ERROR / INFO | Align `sse-swap="event"` listeners with declared or inferred `SSEEvent(event=...)` and `Fragment(target=...)` channels. |
| `sse_speculation` | WARNING | Add `referenced=True` to SSE routes so browser speculation does not open long-lived prefetch streams. |
| `reactive_block` | ERROR | Fix `DependencyIndex` `BlockRef` template or block names. |
| `reactive_cycle` | WARNING | Remove cycles from `DependencyIndex.derive()` relationships. |
| `reactive_paths` | WARNING | Register every declared emitted path in the dependency index or remove stale metadata. |
| `reactive_audience` | WARNING | Pair audience-filtered scopes with `reactive_stream(..., connection=ConnectionInfo(...))`. |
| `live_block_unknown` | ERROR | Fix `live_block` references to unknown templates or blocks. |
| `live_block_unreachable_route` | ERROR | Reference live blocks from reachable routes or remove stale declarations. |

## Forms, Commands, And Safety

| Category | Default severity | Fix target |
|---|---|---|
| `form` | ERROR / WARNING | Align `FormContract` fields with actual `<input>`, `<select>`, and `<textarea>` names. |
| `form_contract` | INFO | Add a `FormContract` to POST routes targeted by static forms, or accept the informational gap. |
| `csrf_form` | WARNING | Add `{{ csrf_field() }}`, `csrf_token()`, or `_csrf_token` to static mutating forms when `CSRFMiddleware` is active. |
| `command` | WARNING | Fix command declarations, route handlers, or command metadata. |
| `commandfor` | WARNING | Fix command target references that cannot be resolved. |
| `vary` | WARNING | Add required `Vary` behavior for cache-sensitive htmx or middleware paths. |
| `allowed_hosts` | ERROR / WARNING | Configure explicit hosts outside development instead of `allowed_hosts=("*",)`. |
| `csrf_session` | ERROR | Register `SessionMiddleware` before `CSRFMiddleware`. |
| `security_stack` | ERROR / WARNING | Wire the secure-by-default stack on apps with mutating routes. Missing `CSRFMiddleware` or `SessionMiddleware` is **ERROR in production, WARNING in staging, silent in development**; missing `SecurityHeadersMiddleware` is always **WARNING** (env-independent). No middleware is force-injected — register the stack yourself (the `chirp new` scaffolds, including `--minimal`, do this for you). This category is the canonical owner of the "mutating route" definition referenced by the forms (`csrf_form`) and auth contracts; `csrf_session` checks ordering and `csrf_form` checks template `<form>` tags, while `security_stack` is the route-level presence check. See the env-severity matrix and the canonical "mutating route" definition below. |
| `csp_nonce` | ERROR / WARNING | Flags an inline-forbidding CSP (`script-src` without `'unsafe-inline'`) that lacks a per-request nonce mechanism while a framework inline-script feature is enabled. As of #195 every framework inline `<script>` — Alpine `safeData`, `safe_target`, `sse_lifecycle`, `delegation`, `view_transitions`, `islands`, `speculation_rules`, and Suspense initial-load scripts (#181) — is built per request from the live nonce, so it is nonced **whenever a nonce mechanism is active** (`CSPNonceMiddleware` or `csp_nonce_enabled=True`, which auto-wires it). The genuinely un-nonceable case is a static `SecurityHeadersMiddleware`/app-level CSP that drops `'unsafe-inline'` *without* a nonce mechanism: then those scripts emit without a nonce and the browser silently blocks them. Severity is env-aware (ERROR in production, WARNING in staging, **silent in development**), mirroring `security_stack`. **Fix:** enable `CSPNonceMiddleware` / `AppConfig(csp_nonce_enabled=True)` so the framework scripts carry the live nonce; or, discouraged, add `'unsafe-inline'` to `script-src`. Stays silent when no inline-forbidding policy is in force, when a nonce mechanism is active (everything nonceable), or when no inline-script feature is enabled. `alpine_csp=True` ships no inline bootstrap and is unaffected. |
| `middleware_signature` | ERROR / WARNING | Make middleware callable as `async __call__(request, next)`. |
| `static_streaming` | WARNING | Keep `StaticFiles` `static_stream_threshold` sane so large static files stream from disk instead of buffering into memory. Warns when the threshold is `<= 0` or effectively unbounded (`>= 1 GiB`). Advisory and env-independent. |
| `secret_key` | ERROR / WARNING | Set a production `secret_key` and use an adequately long value. |
| `nojs_floor` | INFO | Return `FormAction` (303 for plain POST, fragments for htmx) from mutating routes instead of an htmx-only `Fragment`/`OOB`. INFO by default (htmx-only mutation is a valid choice); promote with `override_contract_severity("nojs_floor", Severity.ERROR)` to enforce the no-JS floor. |
| `deploy_debug` | ERROR | Set `debug=False` (or `CHIRP_DEBUG=0`) when `env="production"`. |
| `deploy_metrics` | ERROR | Change `metrics_path` or move the colliding application route so the Prometheus endpoint does not shadow a route. |
| `deploy_sentry` | WARNING | Set a non-zero `sentry_traces_sample_rate` when a Sentry DSN is configured, or clear the DSN. |

### `security_stack`: canonical reference

`security_stack` is the canonical owner of the **mutating route** definition and
the secure-by-default presence check. `rules_nojs_floor` already reuses this
definition (`is_mutating_route` / `MUTATING_METHODS`); the forms (`csrf_form`) and
auth contracts are the intended future consumers, rather than each re-deriving
"what counts as a mutating route."

**What is a mutating route?** A route is mutating when **either** condition
holds:

- It accepts any method in `{POST, PUT, PATCH, DELETE}` — explicit handlers
  (`@app.route("/save", methods=["POST"])`, or `PUT`/`PATCH`/`DELETE`) and
  filesystem `page.py` files that define a `post`/`put`/`patch`/`delete` handler.
- It is a filesystem page that ships `_actions.py` form actions. These pages
  mutate state via POST-to-self dispatched on the `_action` form field. Crucially,
  the `page.py` may declare **only** `get()` — Chirp does *not* auto-register a
  separate POST route variant — so the route is method-`GET` in the router yet is
  unmistakably a mutating surface. The contract treats a page whose discovered
  `actions` is non-empty as mutating, so a GET-only `_actions.py` page is held to
  the same CSRF/Session bar as a POST route (ERROR in production, WARNING in
  staging). Before this was fixed, such a page was a false negative. Because
  `_actions.py` is directory-scoped, every page in a directory that ships one is
  treated as part of that mutating surface — a deliberately conservative,
  fail-loud attribution, since the directory genuinely handles form mutations.

Referenced (transport) routes such as a mutating SSE/API endpoint are
**included** — a mutating endpoint still needs CSRF/session protection, unlike
the no-JS floor (`nojs_floor`), which excludes referenced routes. An app with no
mutating routes emits no `security_stack` issue.

**Env-severity matrix.** Two distinct severity tracks:

| Missing middleware | development | staging | production |
|---|---|---|---|
| `CSRFMiddleware` or `SessionMiddleware` | silent | WARNING | ERROR |
| `SecurityHeadersMiddleware` | WARNING | WARNING | WARNING |

CSRF/Session is env-aware (silent in development so dev apps and shipped examples
stay clean). `SecurityHeadersMiddleware` is a separate, env-independent WARNING
track — missing it warns whenever any mutating route exists, in every env.

**No force-injection.** Per the explicit-over-magic convention, Chirp never
injects security middleware into `App()`. The lever is this contract plus
scaffold defaults: every `chirp new` scaffold (including `--minimal`) wires
`SessionMiddleware` → `CSRFMiddleware` → `SecurityHeadersMiddleware` for you, so
generated apps pass `security_stack` out of the box. `csrf_session` checks the
ordering of that stack; `csrf_form` checks individual template `<form>` tags;
`security_stack` is the route-level presence check.

## Data

| Category | Default severity | Fix target |
|---|---|---|
| `data` | ERROR | Fix `db.fetch(cls, sql)` / `fetch_one` / `stream` SELECT columns that map to no field on the target frozen dataclass. The check is static and conservative: it only fires when the `cls` argument resolves to a module-level frozen dataclass **and** the SQL is a string literal with an explicit `SELECT a, b` list. `SELECT *`, expressions, aggregates, dynamic SQL (f-strings, concatenation), and computed `cls` are skipped silently — no false positives. A SELECTed column is flagged only when it is absent from the dataclass fields **and** (when a declared schema is available from a `migrations` directory) absent from every declared table column — that double-guard keeps the check quiet for columns the dataclass intentionally does not read. HTML-only / db-less apps (no `migrations` dir) emit no `data` issues. Overridable via `app.override_contract_severity("data", Severity.WARNING)`. |

## Debug, Extensions, Accessibility, And Plugins

| Category | Default severity | Fix target |
|---|---|---|
| `debug_wiring` | ERROR | Fix debug/DevTools route, asset, or runtime wiring so diagnostics work in debug mode. |
| `chirpui_runtime` | INFO | Call `use_chirp_ui(app)` or install/configure the optional UI runtime required by ChirpUI templates. |
| `alpine_cdn_url` | ERROR | Replace bare jsDelivr Alpine package URLs with explicit `/dist/cdn.min.js` URLs or Chirp injection helpers. |
| `defer_falsy` | WARNING | Use `{% if key is deferred %}` or `"key" in __chirp_defer_pending__` to distinguish loading from loaded before testing resolved values. |
| `suspense_defer` | WARNING | A template declares a Suspense-deferred key (`is deferred` / `__chirp_defer_pending__`) that no block depends on, so auto-discovery finds nothing to re-render. Reference the key inside a `{% block ... %}`, or pass the blocks explicitly with `Suspense(..., defer_blocks=(...))`. |
| `a11y_interactive` | WARNING | Add keyboard and semantic affordances for interactive elements. |
| `a11y_label` | WARNING | Add visible or accessible labels for form controls. |
| `a11y_alt` | WARNING | Add meaningful `alt` text or intentionally empty decorative `alt=""`. |
| `a11y_heading` | WARNING | Fix skipped or incoherent heading levels. |
| `a11y_landmark` | WARNING | Add page landmarks such as `main`, `nav`, or `header` where expected. |
| `plugin_check_error` | ERROR | Fix a custom check that raised during `app.check()`; the original exception should name the plugin/check. |
