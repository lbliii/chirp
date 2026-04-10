# RFC: htmx 4.0 & Web Platform Alignment

**Status**: Draft
**Date**: 2026-03-25
**Scope**: `src/chirp/server/`, `src/chirp/contracts/`, `src/chirp/http/`, `src/chirp/templating/`
**Related**: RFC Contract Extensions, Hypermedia Landscape Notes (March 2026)

---

## Problem

The hypermedia ecosystem is evolving on three fronts simultaneously:

1. **htmx 4.0 ("The Fetchening")** introduces `<htmx-partial>` — declarative
   fragments without `hx-*` attributes. This aligns perfectly with Chirp's
   "one template, many modes" philosophy but requires content negotiation
   awareness.

2. **Invoker Commands API** (baseline Jan 2026) replaces JavaScript for
   dialogs, popovers, and custom elements via `commandfor`/`command`
   attributes. Chirp's contract validation should extend to cover these
   — a typo in `commandfor` is just as silent as a typo in `hx-target`.

3. **Speculation Rules API** enables instant MPA navigation via browser
   prefetching and prerendering. This directly supports Chirp's "no
   client-side routing" stance — if MPA feels as fast as SPA, there's
   even less reason for client-side routing.

Chirp has the information to support all three: route definitions for
speculation rules, template scanning for invoker validation, and content
negotiation for `<htmx-partial>`. The gap is wiring them together.

---

## Goals

1. **Speculation Rules injection** — automatic `<script type="speculationrules">`
   from route definitions, with tiered opt-in (off/conservative/moderate/eager).
2. **Invoker Commands validation** — `commandfor` target and `command` value
   checks in `chirp check`.
3. **`<htmx-partial>` alignment** — forward-compatible request parsing and
   fragment block resolution for htmx 4.0.
4. **`<htmx-partial>` route validation** — `chirp check` validates that
   `<htmx-partial src="...">` references resolve to registered routes.

### Non-Goals

- Datastar-style reactive signals (Chirp is server-side, not client-side).
- Streaming HTML / Declarative Shadow DOM (research phase, not ready).
- Browser extension or standalone DevTools (existing overlay is sufficient).

---

## Design

### Feature 1: Speculation Rules Injection

**Config**: `AppConfig.speculation_rules: bool | str = False`

| Mode | Behavior |
|------|----------|
| `False` / `"off"` | Inject nothing (default) |
| `True` / `"conservative"` | Prefetch linked pages on hover |
| `"moderate"` | Prefetch eagerly, prerender on hover |
| `"eager"` | Prerender eagerly (routes must be side-effect-free) |

**Implementation**: `src/chirp/server/speculation_rules.py`

Follows the `view_transitions.py` pattern — a normalizer function plus a
snippet builder. The snippet is generated at freeze time from the router:

- Static GET routes → `"source": "list"` with explicit URLs.
- Parametric GET routes → `"source": "document"` with `href_matches` patterns.
- SSE endpoints and non-GET routes are excluded.

Injected via `HTMLInject` middleware (`before="</head>"`, `full_page_only=True`).

The compiler passes the router to `_collect_builtin_middleware` so the
snippet can be generated from actual route definitions rather than config.

### Feature 2: Invoker Commands Validation

**New file**: `src/chirp/contracts/rules_commands.py`

Two checks following the `rules_htmx.py` pattern:

1. **`check_commandfor_targets`** — validates that `commandfor="id"` references
   exist in the template ID set. Reports WARNING with fuzzy suggestion on miss
   (same as `check_hx_target_selectors`).

2. **`check_command_values`** — validates that `command="value"` is a recognized
   built-in command or uses the `--prefix` convention for custom commands.
   Built-in commands: `show-modal`, `close`, `toggle-popover`, `show-popover`,
   `hide-popover`, `request-fullscreen`, `copy`, `cut`, `paste`.

**Integration**: Wired into `check_hypermedia_surface()` after the existing
htmx selector checks. New `commandfor_validated` counter in `CheckResult`.

### Feature 3: `<htmx-partial>` Alignment

**Request parsing**: New `HtmxDetails.partial` property reads the `HX-Partial`
header (anticipated htmx 4.0 header for partial element requests).

**Fragment resolution**: `_resolve_fragment_block()` in `render_plan.py` now
checks the partial name against the fragment target registry before falling
back to `HX-Target`. Priority: explicit block → partial name → HX-Target →
fallback.

**Route validation**: `template_scan.py` gains `extract_htmx_partial_sources()`
which extracts `src=` from `<htmx-partial>` elements. The checker validates
these URLs resolve to registered routes (category: `"htmx_partial"`).

### Already Implemented: Contract Extensions (Phases 1-2)

Dead template detection and SSE fragment validation are already wired into
`checker.py` (lines 383-407 and 138-171 respectively). These were designed
in `rfc-contract-extensions.md` and landed in 0.3.0.

---

## Testing Strategy

1. **Speculation Rules**: Unit tests for normalizer, JSON builder, and snippet
   builder. Fake router with static/parametric/POST/SSE routes to verify
   filtering.
2. **Invoker Commands**: Unit tests for `commandfor` target resolution and
   `command` value recognition. Tests for dynamic value skipping and builtin
   template exclusion.
3. **`<htmx-partial>`**: Unit tests for header parsing, template source
   extraction, and integration test for route validation via
   `check_hypermedia_surface`.

---

## Future Considerations

1. **DevTools: Speculation Rules tab** — show which routes are prerendered,
   prefetch queue state, navigation hit/miss ratios. Would require a new
   JS module in `src/chirp/server/devtools/js/speculation.js`.

2. **DevTools: commandfor visualization** — highlight command→target
   relationships in the element inspector overlay.

3. **Streaming HTML / Declarative Shadow DOM** (`<template shadowrootmode>`) —
   streaming component shells that complement Suspense. Requires design work;
   depends on browser adoption.

4. **Triptych proposals** — browser-native `<html-include>`, declarative HTTP
   methods on forms. Chirp's `Fragment` return type maps directly to these
   if browsers ship native fragment loading. Monitor and adapt.

5. **Fragment cache hit/miss visibility** — if Chirp adds fragment caching,
   show cache status in the DevTools waterfall.
