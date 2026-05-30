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
| `middleware_signature` | ERROR / WARNING | Make middleware callable as `async __call__(request, next)`. |
| `secret_key` | ERROR / WARNING | Set a production `secret_key` and use an adequately long value. |

## Debug, Extensions, Accessibility, And Plugins

| Category | Default severity | Fix target |
|---|---|---|
| `debug_wiring` | ERROR | Fix debug/DevTools route, asset, or runtime wiring so diagnostics work in debug mode. |
| `chirpui_runtime` | INFO | Call `use_chirp_ui(app)` or install/configure the optional UI runtime required by ChirpUI templates. |
| `alpine_cdn_url` | ERROR | Replace bare jsDelivr Alpine package URLs with explicit `/dist/cdn.min.js` URLs or Chirp injection helpers. |
| `defer_falsy` | WARNING | Use `{% if key is deferred %}` or `"key" in __chirp_defer_pending__` to distinguish loading from loaded before testing resolved values. |
| `a11y_interactive` | WARNING | Add keyboard and semantic affordances for interactive elements. |
| `a11y_label` | WARNING | Add visible or accessible labels for form controls. |
| `a11y_alt` | WARNING | Add meaningful `alt` text or intentionally empty decorative `alt=""`. |
| `a11y_heading` | WARNING | Fix skipped or incoherent heading levels. |
| `a11y_landmark` | WARNING | Add page landmarks such as `main`, `nav`, or `header` where expected. |
| `plugin_check_error` | ERROR | Fix a custom check that raised during `app.check()`; the original exception should name the plugin/check. |
