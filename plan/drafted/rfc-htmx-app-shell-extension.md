# RFC: Server-First App-Shell Stability for Chirp

**Status**: Draft  
**Date**: 2026-03-06  
**Scope**: Chirp negotiation, htmx app-shell behavior, `kanban_shell` example  
**Related**: `kanban_shell`, dori app shell, `chirp-ui` fragment patterns

---

## Problem

The app-shell pattern uses `hx-boost` plus inherited `hx-select` on the shell container so boosted navigation can replace only the content region. That inheritance is convenient for full-page navigation, but it is dangerous for nested fragment interactions.

When a child element inside the shell performs an htmx fragment request:

1. it inherits the shell's `hx-select`
2. htmx tries to extract the shell selector from the response
3. fragment responses often do not contain that selector
4. the swap resolves to empty content and the UI appears to "disappear"

This is a real failure mode for inline edit, filter, validation, and other narrow-target updates inside an app shell.

---

## Current State

Chirp already has a server-side mitigation for most fragment responses:

- the central HTML response builder adds `HX-Reselect: *` for `intent="fragment"`
- that header overrides inherited `hx-select` for the response
- this gives fragment responses a single policy point instead of relying on per-element opt-out

However, that policy was incomplete. `ValidationError` responses rendered fragment HTML and marked the response as a fragment, but bypassed the central helper, so they did not get the same `HX-Reselect` override.

That gap is especially harmful in app-shell flows because validation errors are one of the most common fragment responses.

---

## Goals

1. Fragment responses inside an app shell should be safe by default.
2. The fix should live in one server-side policy point, not in dozens of templates.
3. Validation and error flows should behave the same way as success flows.
4. Boosted shell navigation should continue working without introducing a custom client extension.

### Non-Goals

- Rewriting htmx behavior globally.
- Requiring every app to add a custom extension.
- Wrapping every fragment in a fake shell container.
- Solving all app-shell UX issues purely in the client.

---

## Decision

Prefer a server-first solution:

- keep fragment selection override in Chirp negotiation
- ensure all fragment-like responses share the same policy
- treat client-side hooks such as `htmx:beforeSwap` as fallback tools, not the default architecture

### Why Server-First

- Chirp already has a central negotiation layer for response intent.
- `HX-Reselect` is built into htmx and is specifically designed to override inherited `hx-select`.
- server-side normalization is easier to reason about than target-based client heuristics
- client heuristics tend to hard-code shell IDs such as `#main` or `#page-content`, which does not scale well across layouts

---

## Proposed Policy

Any response Chirp considers a fragment should be emitted through one code path that applies the fragment override policy.

In practice, that means:

1. use `_html_response(..., intent="fragment")` for fragment HTML wherever possible
2. ensure `ValidationError` uses the same path as `Fragment`, `Page`, `LayoutPage`, `OOB`, and fragment `FormAction`
3. verify this behavior with tests at both negotiation level and app-shell example level

### Central Rule

If `render_intent == "fragment"`, the response should include:

```http
HX-Reselect: *
```

This keeps fragment swaps safe even when the triggering element inherits shell-level `hx-select`.

---

## Implementation

### 1. Normalize Negotiation

Update negotiation so `ValidationError` uses the same fragment response builder as the other fragment branches.

This removes the special-case gap where validation errors were fragment-shaped responses but did not inherit the fragment-safe header policy.

### 2. Add Regression Tests

Add negotiation assertions that fragment responses include `HX-Reselect`, including:

- plain `Fragment`
- `ValidationError`
- tuple-wrapped `ValidationError`
- tuple-wrapped `Fragment`

Add app-shell regression coverage in `kanban_shell` for representative shell interactions:

- boosted fragment navigation
- inline edit form load
- invalid save returning `422`
- filter requests targeting `#board`
- add-form validation failures

### 3. Keep Example Test Harness Working

The example test harness must be able to exercise real authenticated fragment flows. That includes keeping the example import path and auth checks aligned with Chirp's current auth model so shell regressions are testing the intended routes rather than getting redirected before the fragment swap happens.

---

## Alternatives Considered

### A. Per-Element `hx-disinherit`

Rejected as the default approach.

It works, but it creates poor DX:

- easy to forget
- fragile during refactors
- spreads shell correctness across many templates

### B. Custom htmx Extension

Not the preferred architecture.

A custom extension would need to infer whether a request is "full-page navigation" or "narrow fragment update" from client-side state such as target selectors. That is more brittle than using Chirp's server-side render intent.

This remains an escape hatch if a future scenario cannot be expressed through response negotiation, but it should not be the first choice.

### C. `htmx:beforeSwap` Listener

Viable as a fallback, not the default.

`htmx:beforeSwap` and `selectOverride` can override inherited `hx-select`, but they still rely on client-side detection heuristics. That makes them useful for one-off integrations, but less attractive than a server policy for framework behavior.

### D. Wrapping Fragments in `#page-content`

Rejected.

It couples fragment responses to shell markup and risks invalid or duplicated IDs.

---

## Open Questions

1. Is `HX-Reselect: *` the final selector we want to standardize on for all fragment responses, or should Chirp expose that as a more explicit helper in response construction?
2. Should the fragment-safe policy eventually extend to additional response builders outside negotiation, if new ones are introduced?
3. Should app-shell docs explicitly warn that mounted pages used in boosted navigation should set a fragment-safe page root such as `page_block_name="page_root"`?

---

## Validation

Success looks like:

- fragment responses no longer collapse content inside inherited shell selectors
- `422` validation responses behave like other fragment responses
- the negotiation suite asserts the fragment override policy directly
- `kanban_shell` has targeted regression tests for representative shell interactions
- the architecture no longer depends on a custom extension for the common case

---

## References

- [htmx `hx-select`](https://htmx.org/attributes/hx-select/)
- [htmx response headers](https://htmx.org/docs/#response-headers)
- [htmx events: `beforeSwap`](https://htmx.org/events/#event-htmx-beforeSwap)
- [htmx inheritance issue discussion](https://github.com/bigskysoftware/htmx/issues/2865)
- `src/chirp/server/negotiation.py`
- `tests/test_negotiation.py`
- `examples/chirpui/kanban_shell/test_app.py`
