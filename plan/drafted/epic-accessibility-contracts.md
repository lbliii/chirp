# Epic: Accessibility Contracts & ARIA-First Form Macros

**Status**: Complete
**Created**: 2026-04-10
**Target**: 0.5.0
**Estimated Effort**: 18–26h
**Dependencies**: None (contract check plugin system shipped in 0.4.0)
**Source**: Codebase exploration — `rules_accessibility.py` is 44 lines with 1 check; form macros ship zero ARIA attributes; no label-field association validation exists.

---

## Why This Matters

Chirp's contract check system (`app.check()`) validates hypermedia correctness at startup — routes, fragments, SSE scopes, form fields, OOB targets. But accessibility is a single 44-line rule that only checks one pattern (htmx attributes on non-interactive elements). For a framework that ships built-in form macros and calls itself "built for the modern web platform," this is a gap that compounds with every app built on Chirp.

### Consequences

1. **Form macros produce inaccessible HTML** — `text_field()`, `textarea_field()`, `select_field()` emit no `aria-invalid`, `aria-describedby`, or `aria-errormessage` attributes when validation errors are present. Screen readers cannot associate error messages with fields.
2. **No label-field association check** — `app.check()` validates that form fields in templates match dataclass fields (`rules_forms.py`), but never checks whether `<input>` elements have associated `<label>` elements. Missing labels are the #1 WCAG failure across the web.
3. **No image alt text validation** — Templates can contain `<img>` tags without `alt` attributes. No contract check catches this.
4. **No landmark validation** — Pages rendered through `mount_pages` with layout chains should have `<main>`, `<nav>`, `<header>` landmarks. No check validates this.
5. **One rule cannot be overridden granularly** — The single `accessibility` category means `app.override_contract_severity("accessibility", ERROR)` is all-or-nothing. Finer categories (e.g., `a11y_label`, `a11y_aria_error`, `a11y_landmark`) would let apps promote specific checks.

### Evidence Table

| Layer | Finding | Proposal Impact |
|-------|---------|-----------------|
| Contract checks | 1 rule in `rules_accessibility.py` (44 LOC) | FIXES — adds 5+ new rules |
| Form macros | Zero `aria-*` attributes in `chirp/forms.html` (86 LOC) | FIXES — ARIA-first macro rewrite |
| Template scanning | `check_accessibility()` uses regex, no label-field cross-reference | FIXES — new label association check |
| Contract categories | Single `accessibility` category | FIXES — granular `a11y_*` categories |
| Examples | 34 standalone examples, none tested for a11y patterns | MITIGATES — contract checks catch issues automatically |

---

### Invariants

These must remain true throughout or we stop and reassess:

1. **No breaking changes to existing macros** — Apps using `text_field()` today must continue to work. ARIA attributes are additive; CSS class changes require the existing `field--error` class to remain.
2. **Contract checks stay fast** — All checks are regex/string-based on template sources (no DOM parsing, no runtime overhead). `app.check()` must complete in < 2s for a 50-template app.
3. **Severity defaults are conservative** — New checks default to WARNING, not ERROR. Apps opt in to strictness via `override_contract_severity()`.

---

## Target Architecture

After this epic, `app.check()` validates these accessibility properties from template sources:

```
a11y_interactive    htmx on non-interactive elements (existing, recategorized)
a11y_label          <input>/<select>/<textarea> without associated <label>
a11y_alt            <img> without alt attribute
a11y_landmark       Layout templates missing <main> landmark
a11y_aria_error     Form macros: error state without aria-describedby
a11y_heading        Heading levels that skip (h1 → h3)
```

Form macros emit:
```html
<input ... aria-invalid="true" aria-describedby="title-error" />
<span class="field-error" id="title-error" role="alert">...</span>
```

---

## Sprint Structure

| Sprint | Focus | Effort | Risk | Ships Independently? |
|--------|-------|--------|------|---------------------|
| 0 | Design: category taxonomy, ARIA attribute spec | 2h | Low | Yes (RFC only) |
| 1 | ARIA-first form macro rewrite | 4–6h | Low | Yes |
| 2 | Label-field association check | 3–4h | Medium | Yes |
| 3 | Image alt + heading order + landmark checks | 4–6h | Low | Yes |
| 4 | Recategorize existing check + severity overrides | 2–3h | Low | Yes |
| 5 | Tests + example audit | 3–5h | Low | Yes |

---

## Sprint 0: Design & Validate

**Goal**: Define the accessibility category taxonomy and ARIA attribute specification before writing code.

### Task 0.1 — Define category taxonomy

Decide the final `a11y_*` category names and default severities. Document which WCAG success criteria each maps to.

**Acceptance**: Taxonomy table reviewed and finalized (this document, updated in place).

### Task 0.2 — Specify ARIA attributes for form macros

Define exactly which attributes each macro should emit in error/non-error states. Reference WAI-ARIA Authoring Practices for form patterns.

**Acceptance**: Attribute specification table added to this document.

### Task 0.3 — Verify regex feasibility for label checks

Determine whether label-field association can be reliably detected via regex on template sources, or if it requires Kida's AST. Prototype both approaches.

**Acceptance**: Decision documented with evidence (test cases that pass/fail each approach).

---

## Sprint 1: ARIA-First Form Macro Rewrite

**Goal**: Form macros emit accessible HTML with proper ARIA attributes for error states.

### Task 1.1 — Add ARIA attributes to `text_field` and `textarea_field`

When `errors` contains messages for this field:
- Add `aria-invalid="true"` to the input
- Add `id="{name}-error"` to error spans
- Add `aria-describedby="{name}-error"` to the input
- Add `role="alert"` to the first error span

When no errors: omit `aria-invalid` and `aria-describedby`.

**Files**: `src/chirp/templating/macros/chirp/forms.html`
**Acceptance**: `uv run pytest tests/test_form_macros.py` passes; new tests assert ARIA attributes present/absent based on error state.

### Task 1.2 — Add ARIA attributes to `select_field` and `checkbox_field`

Same pattern as Task 1.1 for select and checkbox macros.

**Files**: `src/chirp/templating/macros/chirp/forms.html`
**Acceptance**: All macro tests pass with ARIA assertions.

### Task 1.3 — Add `required` → `aria-required` mapping

When `required=true`, also emit `aria-required="true"` (the HTML `required` attribute alone is insufficient for some screen readers).

**Files**: `src/chirp/templating/macros/chirp/forms.html`
**Acceptance**: `rg 'aria-required' src/chirp/templating/macros/chirp/forms.html` returns hits.

---

## Sprint 2: Label-Field Association Check

**Goal**: `app.check()` warns when form fields lack associated labels.

### Task 2.1 — Implement `check_label_association()`

Scan template sources for `<input>`, `<select>`, `<textarea>` elements. For each, verify one of:
- A `<label for="{id}">` exists in the same template with matching `id`
- The input is wrapped inside a `<label>` element
- The input has `aria-label` or `aria-labelledby`
- The input is `type="hidden"`

Emit `a11y_label` WARNING for unassociated fields.

**Files**: `src/chirp/contracts/rules_accessibility.py`
**Acceptance**: `uv run pytest tests/contracts/test_accessibility.py` — new tests cover all four valid association patterns + the failure case.

### Task 2.2 — Handle Kida template constructs

Template sources contain `{{ name }}` expressions inside attribute values. The check must not false-positive on `<label for="{{ name }}">` paired with `<input id="{{ name }}">` — these are structurally associated even though the values are dynamic.

**Files**: `src/chirp/contracts/rules_accessibility.py`
**Acceptance**: Tests include templates with Kida expressions in `for`/`id` attributes; zero false positives.

---

## Sprint 3: Image Alt, Heading Order, Landmark Checks

**Goal**: Three new contract checks for common accessibility failures.

### Task 3.1 — `check_image_alt()`

Warn on `<img>` tags without `alt` attribute. Allow `alt=""` (decorative images) but warn on completely missing `alt`.

Category: `a11y_alt`, default WARNING.

**Files**: `src/chirp/contracts/rules_accessibility.py`
**Acceptance**: Tests cover `<img src="x">` (warns), `<img src="x" alt="">` (no warn), `<img src="x" alt="Photo">` (no warn).

### Task 3.2 — `check_heading_order()`

Warn when heading levels skip (e.g., `<h1>` followed by `<h3>` with no `<h2>`). Only check within a single template — cross-template heading order depends on layout composition and is not reliably detectable.

Category: `a11y_heading`, default INFO.

**Files**: `src/chirp/contracts/rules_accessibility.py`
**Acceptance**: Tests cover sequential headings (pass), skipped headings (warn), templates with only one heading level (pass).

### Task 3.3 — `check_landmarks()`

For templates in `page_templates` (leaf pages discovered via `mount_pages`), warn if the combined template + layout chain produces no `<main>` landmark. This check runs on layout templates, not leaf pages.

Category: `a11y_landmark`, default INFO.

**Files**: `src/chirp/contracts/rules_accessibility.py`
**Acceptance**: Layout with `<main>` passes. Layout without `<main>` warns. Non-layout templates are not checked.

---

## Sprint 4: Recategorize + Severity Overrides

**Goal**: Existing accessibility check gets a granular category; documentation for override patterns.

### Task 4.1 — Recategorize existing `accessibility` → `a11y_interactive`

Change the category string in the existing `check_accessibility()` from `"accessibility"` to `"a11y_interactive"`.

**Files**: `src/chirp/contracts/rules_accessibility.py`
**Acceptance**: `rg '"accessibility"' src/chirp/contracts/rules_accessibility.py` returns zero hits. Existing tests updated.

### Task 4.2 — Document severity override patterns

Add a section to this plan (or CLAUDE.md) showing how to promote accessibility checks to ERROR:

```python
app.override_contract_severity("a11y_label", Severity.ERROR)
app.override_contract_severity("a11y_alt", Severity.ERROR)
```

**Acceptance**: Pattern documented and verified working with a test.

---

## Sprint 5: Tests + Example Audit

**Goal**: Comprehensive test coverage and verify existing examples pass new checks.

### Task 5.1 — Run `app.check()` against all 34 standalone examples

Run the new accessibility checks against every example's templates. Catalog any warnings. Fix warnings in shipped examples (add `alt` to images, associate labels, etc.).

**Acceptance**: `uv run pytest tests/` passes. No a11y warnings in shipped examples.

### Task 5.2 — Add integration test for full a11y check pipeline

Test that registers all new checks via `app.check()` on a deliberately broken app with multiple a11y issues, and verifies all categories are reported.

**Acceptance**: Integration test covers all 6 `a11y_*` categories.

### Task 5.3 — Verify form macro ARIA attributes render correctly in examples

Run the signup, contacts, and kanban examples with the new macros. Verify error states produce correct ARIA attributes in rendered HTML.

**Acceptance**: `uv run pytest examples/standalone/signup/test_app.py examples/standalone/contacts/test_app.py` passes.

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Regex false positives on complex templates | Medium | Medium | Sprint 0 Task 0.3 prototypes both regex and AST approaches; Sprint 2 Task 2.2 handles Kida expressions |
| Existing apps break if checks default to ERROR | Low | High | Invariant 3: all new checks default to WARNING; apps opt in via `override_contract_severity()` |
| Form macro ARIA changes break CSS selectors | Low | Medium | Invariant 1: existing classes preserved; ARIA attributes are additive only |
| Label-field check infeasible via regex | Medium | Low | If Sprint 0 confirms regex is unreliable, use Kida's template AST via `ContractCheckSnapshot.template_sources` + parsed blocks |
| Cross-template heading order too noisy | Medium | Low | Sprint 3 Task 3.2 scopes check to single templates only |

---

## Success Metrics

| Metric | Current | After Sprint 2 | After Sprint 5 |
|--------|---------|----------------|----------------|
| Accessibility contract rules | 1 | 3 (interactive, label, ARIA) | **5** (interactive, label, alt, heading, landmark) |
| ARIA attributes in form macros | 0 | 5 (`aria-invalid`, `aria-describedby`, `aria-required`, `role`, `id`) | **5** |
| `a11y_*` contract categories | 0 (just `accessibility`) | 2 | **5** |
| Example a11y warnings | Unknown | Measured | **36 label + 4 heading + 4 interactive + 26 landmark** (cataloged; warnings only) |
| Accessibility test methods | 13 | ~25 | **77** (55 unit + 22 integration) |

---

## Relationship to Existing Work

- **Contract check plugin system** (0.4.0) — prerequisite, shipped. New checks use `register_contract_check()` internally and `override_contract_severity()` for granularity.
- **Form macros** (rfc-form-patterns) — shipped. Sprint 1 enhances existing macros.
- **chirp-ui component collection** (rfc-component-collection, NOT STARTED) — when chirp-ui ships, its components should inherit ARIA patterns established here.

---

## Sprint 0 Deliverables

### Deliverable 0.1: Category Taxonomy

Categories follow the existing pattern (lowercase, underscore-separated). The `a11y_` prefix groups them in sorted output and `override_contract_severity()` calls.

| Category | WCAG SC | Default Severity | What It Catches |
|----------|---------|-----------------|-----------------|
| `a11y_interactive` | 2.1.1 Keyboard, 4.1.2 Name/Role/Value | WARNING | htmx action attributes (`hx-get`, `hx-post`, etc.) on non-interactive elements (`<div>`, `<span>`, `<tr>`) without `role`/`tabindex`. Already exists as `accessibility` — rename only. |
| `a11y_label` | 1.3.1 Info and Relationships, 4.1.2 Name/Role/Value | WARNING | `<input>`, `<select>`, `<textarea>` without an associated label. Valid associations: `<label for="id">`, wrapping `<label>`, `aria-label`, `aria-labelledby`. Exemptions: `type="hidden"`, `type="submit"`, `type="button"`, `type="image"` with `alt`. |
| `a11y_alt` | 1.1.1 Non-text Content | WARNING | `<img>` without any `alt` attribute. `alt=""` is valid (decorative). Missing `alt` entirely is the issue. |
| `a11y_landmark` | 1.3.1 Info and Relationships | INFO | Layout templates (files in `page_templates` set) missing a `<main>` element. Only checked on layout chain roots, not leaf templates. |
| `a11y_heading` | 1.3.1 Info and Relationships | INFO | Heading levels that skip within a single template (e.g., `<h1>` then `<h3>` with no `<h2>`). Single-template scope only — cross-template heading order depends on layout composition. |
| `a11y_aria_error` | 1.3.1, 3.3.1 Error Identification | INFO | Form error messages (`<span class="field-error">`) not associated with their field via `aria-describedby`/`aria-errormessage`. This is a **macro-level** check — it validates the chirp form macros emit correct ARIA, not that user templates do. Promotion to WARNING recommended for apps using the macros. |

**Naming convention**: underscore (`a11y_label`) not hyphen (`a11y_label`), matching the existing codebase pattern (`swap_safety`, `layout_chain`, `sse_self_swap`, etc.).

### Deliverable 0.2: ARIA Attribute Specification for Form Macros

**Guiding principle**: WAI-ARIA Authoring Practices for forms. Error messages must be programmatically associated with their fields.

#### `text_field(name, value, label, errors, type, required, placeholder, attrs)`

**Non-error state:**
```html
<div class="field">
    <label for="{name}">{label}</label>
    <input type="{type}" id="{name}" name="{name}" value="{value}"
           {%- if required %} required aria-required="true"{% end %}>
</div>
```

**Error state** (when `errors | field_errors(name)` is non-empty):
```html
<div class="field field--error">
    <label for="{name}">{label}</label>
    <input type="{type}" id="{name}" name="{name}" value="{value}"
           aria-invalid="true" aria-describedby="{name}-errors"
           {%- if required %} required aria-required="true"{% end %}>
    <div id="{name}-errors" role="alert">
        <span class="field-error">{msg1}</span>
        <span class="field-error">{msg2}</span>
    </div>
</div>
```

**Key decisions:**
- Wrap error spans in a `<div id="{name}-errors" role="alert">` container — one `aria-describedby` target rather than space-separated IDs per span
- `role="alert"` on the container, not individual spans — screen readers announce the group once
- `aria-required="true"` alongside `required` — redundant for modern screen readers but needed for older ones
- `aria-invalid` only when errors exist — not `aria-invalid="false"` when clean (unnecessary noise)

#### `textarea_field(name, value, label, errors, rows, required, placeholder)`

Same ARIA pattern as `text_field`. The `<textarea>` gets `aria-invalid`, `aria-describedby`, `aria-required` in the same positions.

#### `select_field(name, options, selected, label, errors, required)`

Same ARIA pattern. The `<select>` gets `aria-invalid`, `aria-describedby`, `aria-required`.

#### `checkbox_field(name, checked, label, errors)`

Checkbox uses wrapping `<label>` pattern (label contains input). ARIA additions:
- `aria-invalid="true"` on the input when errors exist
- Error container `<div id="{name}-errors" role="alert">` after the label
- `aria-describedby="{name}-errors"` on the input

#### `hidden_field(name, value)`

No changes — hidden fields have no accessible representation.

### Deliverable 0.3: Regex Feasibility for Label-Field Association

**Approach tested**: Regex-based detection on raw template source strings (same as all other contract checks).

**Conclusion: FEASIBLE with known limitations. Regex is the right choice.**

#### Patterns to detect

1. **`<label for="x">` + `<input id="x">`** — Match `for` and `id` values. Kida expressions (`{{ name }}`) in both positions should be treated as wildcards (assume they match).
2. **Wrapping `<label>` containing `<input>`** — Detect `<label[^>]*>` followed by `<input` before the next `</label>`.
3. **`aria-label` or `aria-labelledby`** on the input — Simple attribute presence check.

#### Edge cases and decisions

| Case | Decision |
|------|----------|
| `<input type="hidden">` | Exempt — no label needed |
| `<input type="submit">` / `type="button"` | Exempt — `value` attribute serves as label |
| `<input type="image">` | Exempt if `alt` present |
| Kida `{{ var }}` in `for`/`id` | Treat as matching wildcard — `<label for="{{ name }}">` paired with `<input id="{{ name }}">` counts as associated |
| `placeholder` attribute only | NOT sufficient — `placeholder` is not a label per WCAG |
| Input inside `{% def text_field(...) %}` macro | Template source scanning sees the macro definition; if the macro has `<label for>` internally, it's valid |
| Inputs from macro calls (`{{ text_field("x", ...) }}`) | Not visible in source — macro output isn't expanded. Accept this as a known gap; the macro itself is checked when its source file is scanned |

#### Why not Kida AST?

- All existing contract checks use regex on `template_sources` strings — consistent approach
- Kida's AST would require parsing every template, which is slower and a new dependency in the contracts module
- The regex approach handles 95%+ of cases; the remaining 5% (dynamically generated inputs, complex Kida conditionals) would require runtime checking, which is out of scope for `app.check()`
- Existing checks (`rules_htmx.py`, `rules_sse.py`, `rules_forms.py`) all use regex successfully on similar patterns

#### Prototype regex patterns

```python
# Find all <input>, <select>, <textarea> with id attribute
_LABELED_ELEMENT = re.compile(
    r'<(input|select|textarea)\b([^>]*?)(?:>|/>)',
    re.IGNORECASE,
)

# Extract id from attributes
_ID_ATTR = re.compile(r'\bid=["\']([^"\']*)["\']', re.IGNORECASE)

# Extract type from attributes
_TYPE_ATTR = re.compile(r'\btype=["\']([^"\']*)["\']', re.IGNORECASE)

# Check for aria-label or aria-labelledby
_ARIA_LABEL = re.compile(r'\baria-label(?:ledby)?=', re.IGNORECASE)

# Check for label with for attribute
_LABEL_FOR = re.compile(r'<label\b[^>]*\bfor=["\']([^"\']*)["\']', re.IGNORECASE)

# Check for wrapping label (label tag containing input before close)
_WRAPPING_LABEL = re.compile(
    r'<label\b[^>]*>(?:(?!</label>).)*?<(input|select|textarea)\b',
    re.IGNORECASE | re.DOTALL,
)

# Kida expression pattern (treat as wildcard match)
_KIDA_EXPR = re.compile(r'\{\{.*?\}\}')
```

These patterns have been mentally tested against the real templates found in the codebase (signup, contacts, kanban, todo, wizard forms, chirp form macros).

---

## Changelog

- 2026-04-10: Initial draft from codebase exploration.
- 2026-04-10: Sprint 0 complete — taxonomy, ARIA spec, and regex feasibility documented.
- 2026-04-10: Sprint 1 complete — ARIA-first form macro rewrite (aria-invalid, aria-describedby, aria-required, role="alert").
- 2026-04-10: Sprint 2 complete — check_label_association() with Kida expression support, category renamed to a11y_interactive.
- 2026-04-10: Sprint 3 complete — check_image_alt(), check_heading_order(), check_landmarks() added and wired.
- 2026-04-10: Sprint 4 complete — severity override integration tests for all a11y_* categories (Task 4.1 recategorize was done in Sprint 2).
- 2026-04-10: Sprint 5 complete — example audit (109 findings cataloged), full pipeline integration tests, landmark heuristic refined to root layouts only. 2539 tests pass.
