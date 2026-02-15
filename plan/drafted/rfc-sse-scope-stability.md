# RFC: SSE Scope Stability — Component Pattern & Fail-Fast Validation

**Status**: Implemented (component + validation)  
**Date**: 2026-02-15  
**Problem**: Complex layouts have deeply nested `#main` (or equivalent) nodes. SSE/WebSocket fragments inside them inherit `hx-target` and wipe the whole tree. Relying on developers to remember `hx-disinherit` is unsustainable.

---

## Problem Statement

When `sse-connect` lives inside any ancestor with `hx-target` (body, main, hx-boost container, nested layouts), fragments swap into the wrong place. One OOB div replaces the entire content area. Deep nesting makes this worse — inheritance chains are long and non-obvious.

**Current mitigation**: Add `hx-disinherit="hx-target hx-swap"` on every `sse-connect`. Easy to forget, especially when copying examples or scaffolding.

---

## Design Options

### Option A: Reusable SSE Scope Component (Recommended)

**Idea**: A single partial/macro that is the canonical way to add SSE. It always includes `hx-disinherit`. Use it, get correct behavior.

**Implementation**:

1. Ship `chirp/templates/chirp/sse_scope.html` (or equivalent) with chirp or chirp-ui.
2. Template usage:

```html
{% include "chirp/sse_scope.html" with url="/events", swap="fragment" %}
```

Renders:

```html
<div hx-ext="sse" sse-connect="/events" hx-disinherit="hx-target hx-swap">
  <div sse-swap="fragment" class="sse-sink"></div>
</div>
```

**Pros**: Single source of truth, impossible to forget hx-disinherit, works with any nesting depth.  
**Cons**: Requires kida/jinja `include`; some apps may prefer raw HTML.  
**Effort**: Low — one partial, document it.

---

### Option B: `data-chirp-sse-scope` Semantic Attribute

**Idea**: A Chirp-specific attribute that expands to the correct htmx attributes at render time. Chirp (or a kida extension) would process templates and replace it.

```html
<div data-chirp-sse-scope sse-connect="/events">
  <div sse-swap="fragment"></div>
</div>
```

→ Chirp injects `hx-ext="sse" hx-disinherit="hx-target hx-swap"` on the element.

**Pros**: Declarative, self-documenting.  
**Cons**: Requires Chirp to parse/modify HTML output; adds framework-specific concept; breaks "plain HTML" philosophy.  
**Effort**: Medium — template post-processing or custom kida node.

---

### Option C: Upgrade `chirp check` to ERROR

**Idea**: `sse_scope` and `swap_safety` already detect the problem. Upgrade severity from WARNING to ERROR so the build fails.

**Implementation**: In `contracts.py`, change `Severity.WARNING` to `Severity.ERROR` for `sse_scope` when `sse-connect` lacks `hx-disinherit` and broad targets exist.

**Pros**: Zero new concepts, catches mistakes before deploy, works with any template structure.  
**Cons**: Fails the build — teams must fix before shipping. Some may want to suppress.  
**Effort**: Trivial — one-line change + config flag to allow downgrade if needed.

---

### Option D: Upstream htmx-ext-sse Change

**Idea**: The SSE extension could default `sse-connect` to not inherit `hx-target`. The swap target would always be the `sse-swap` element.

**Implementation**: PR to bigskysoftware/htmx-ext-sse. When processing an SSE event, use the sse-swap element as the target for non-OOB content, regardless of inheritance.

**Pros**: Fixes the problem for all htmx users, not just Chirp.  
**Cons**: External dependency, may break existing apps that rely on inheritance, upstream may reject.  
**Effort**: Medium — need to understand extension internals.

---

## Implemented: A + C

1. **Component (A)**: Added `chirp/templating/macros/chirp/sse.html` with `sse_scope` macro. Usage: `{% from "chirp/sse" import sse_scope %}` then `{{ sse_scope("/events") }}`. Always includes `hx-disinherit`.
2. **Validation (C)**: Upgraded `sse_scope` contract check from WARNING to ERROR. `chirp check` fails if raw `sse-connect` lacks `hx-disinherit` inside a broad target.

**Result**: 
- Use the component → correct by default, works at any depth.
- Use raw HTML → `chirp check` fails. Fix by using `sse_scope` or adding `hx-disinherit`.

---

## Component API (Option A Detail)

**File**: `chirp/templates/chirp/sse_scope.html` (or in chirp-ui if that ships first)

**Parameters**:
- `url` (required): SSE endpoint path
- `swap` (default: `"fragment"`): Event name for sse-swap
- `class` (optional): Extra CSS classes for the wrapper
- `sink_class` (default: `"sse-sink"`): Class for the inner swap target (often `display:none`)

**Rendered output**:
```html
<div hx-ext="sse" sse-connect="{{ url }}" hx-disinherit="hx-target hx-swap" class="{{ class }}">
  <div sse-swap="{{ swap }}" class="{{ sink_class }}"></div>
</div>
```

**Usage in hackernews**:
```html
{% include "chirp/sse_scope.html" with url="/events" %}
```

---

## Open Questions

1. **Where does the component live?** Chirp core (adds template dir) vs chirp-ui (separate package). Chirp core is minimal; a single partial might be acceptable.
2. **Kida vs Jinja syntax?** Chirp uses Kida. Kida has `{% include %}`. Need to verify parameter passing.
3. **ERROR strictness**: Should there be a `--no-sse-scope-error` flag for gradual migration?
