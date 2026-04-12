# Epic: Harden bsite-discoveries — Land the Hierarchical Shell Swap PR

**Status**: Draft
**Created**: 2026-04-12
**Target**: 0.4.0 (Unreleased)
**Estimated Effort**: 6–10h
**Dependencies**: chirp-ui package update (for `make_route_link_attrs`)
**Source**: Deep analysis of `lbliii/monterrey-v4` branch (16 commits, 64 files, +5 532 lines against main)

---

## Why This Matters

The bsite-discoveries branch introduces **declarative, layout-aware navigation swap resolution** — the single largest architectural addition since Suspense. It moves the framework from manual `hx-target` authoring to framework-computed swap scopes based on layout chain metadata. The branch is feature-complete but has **two regressions and several hardening gaps** that block a clean merge.

### Consequences of merging as-is

1. **`_cross_shell_boost_redirect` breaks basic mounted-pages apps** — boosted GETs to apps without chirp-ui produce empty-body 200s with `hx-redirect` instead of rendered content (26 test failures cascade from this)
2. **`use_chirp_ui()` crashes on import** — references `make_route_link_attrs` which doesn't exist in the installed chirp-ui package (blocks all chirp-ui integration tests)
3. **No integration test for cross-shell redirect** — the safety net that catches client/server target mismatches is untested in a real app context
4. **Layout OOB on streaming responses** — code path added but no integration test verifies OOB blocks append correctly to Suspense/TemplateStream
5. **`defer_blocks` accepts nonexistent block names silently** — typos in explicit block lists produce no warning, blocks are just skipped
6. **Navigation swap `swap_attrs` LookupError path** — returns `{}` outside request context, correct but untested

### Evidence Table

| Source | Finding | Proposal Impact |
|--------|---------|-----------------|
| `test_shell_actions_e2e.py` failure | `_cross_shell_boost_redirect` returns redirect for apps with empty `swap_scope_map` | FIXES (Sprint 1) |
| `test_chirpui_boundary.py` failure | `make_route_link_attrs` import doesn't exist in installed chirp-ui | FIXES (Sprint 1) |
| `test_handler.py` (new tests) | Cross-shell redirect has synthetic tests only; no mounted-pages integration | FIXES (Sprint 2) |
| `negotiation_oob.py:193` | `_KidaBlockAdapter.template_metadata()` catches bare `Exception` | FIXES (Sprint 2) |
| `suspense.py` `defer_blocks` | No validation that listed blocks exist in the template | FIXES (Sprint 2) |
| `navigation_swap.py:114` | `lookup_layout_chain_for_path` tested synthetically only | MITIGATES (Sprint 2) |
| `streaming_html.py` + `AlpineInject` | No integration test with real Suspense response | FIXES (Sprint 3) |

---

### Invariants

1. **Existing tests stay green**: All tests that pass on `main` must pass after every sprint. No regressions permitted.
2. **Backward compatibility preserved**: Apps without navigation metadata (`swap_scope_map`, `domain`, `shell` annotations) must behave identically to `main`.
3. **Each sprint ships independently**: Every PR is mergeable alone; later sprints can be deferred without breaking earlier work.

---

## Target Architecture

No new architecture needed — the branch already implements the design. The target is a **green test suite** with **hardened edge cases** and **guarded external dependencies**.

```
handler.py: _cross_shell_boost_redirect
  └─ Bail early when swap_scope_map is empty (no metadata = no enforcement)
  └─ Bail early when HX-Current-URL is missing (can't compute swap diff)

chirp_ui.py: use_chirp_ui()
  └─ Guard make_route_link_attrs import with try/except ImportError
  └─ Degrade gracefully when chirp-ui doesn't export it yet

suspense.py: defer_blocks validation
  └─ Warn (not error) when a listed block doesn't exist in the template

negotiation_oob.py: _KidaBlockAdapter
  └─ Narrow Exception catch to specific template errors
```

---

## Sprint Structure

| Sprint | Focus | Effort | Risk | Ships Independently? |
|--------|-------|--------|------|---------------------|
| 0 | Design: review this plan | 0.5h | Low | Yes (plan only) |
| 1 | Fix regressions (redirect + import) | 1–2h | Low | Yes |
| 2 | Harden edge cases (validation, error handling) | 2–3h | Medium | Yes |
| 3 | Integration tests (streaming + cross-shell) | 2–3h | Medium | Yes |

---

## Sprint 0: Review & Validate Plan

**Goal**: Confirm the two regressions reproduce and the fixes are correct before writing code.

### Task 0.1 — Reproduce `_cross_shell_boost_redirect` regression

Run `uv run pytest tests/test_shell_actions_e2e.py -x` and confirm the failure is an `hx-redirect` on a boosted GET to a basic mounted-pages app.

**Acceptance**: Failure message shows `Response.text == ''` with `hx-redirect` header.

### Task 0.2 — Reproduce `make_route_link_attrs` import error

Run `uv run pytest tests/test_chirpui_boundary.py -x` and confirm `ImportError: cannot import name 'make_route_link_attrs'`.

**Acceptance**: Failure traceback shows the exact import path.

---

## Sprint 1: Fix Regressions

**Goal**: Unblock the test suite by fixing the two blocking issues.

### Task 1.1 — Guard `_cross_shell_boost_redirect` for empty swap metadata

In `src/chirp/server/handler.py`, add `not swap_scope_map` to the early-return guard at line 88. When no swap scopes are configured, the cross-shell redirect logic has no metadata to enforce and must be a no-op.

**Files**: `src/chirp/server/handler.py:82-89`
**Acceptance**: `uv run pytest tests/test_shell_actions_e2e.py -x` passes. `uv run pytest tests/test_handler.py -x` passes.

### Task 1.2 — Guard `make_route_link_attrs` import in chirp_ui

In `src/chirp/ext/chirp_ui.py`, wrap the `from chirp_ui.filters import make_route_link_attrs` in a `try/except ImportError` block. When chirp-ui doesn't export it yet, skip the route link integration gracefully.

**Files**: `src/chirp/ext/chirp_ui.py:128`
**Acceptance**: `uv run pytest tests/test_chirpui_boundary.py -x` passes. `uv run pytest tests/contracts/test_page_shell.py -x` passes.

### Task 1.3 — Verify cascade

**Acceptance**: `uv run pytest --tb=short -q` shows zero failures (ERRORs from missing chirp-ui example deps are acceptable).

---

## Sprint 2: Harden Edge Cases

**Goal**: Tighten error handling and add validation for developer-facing APIs.

### Task 2.1 — Validate `defer_blocks` names at render time

In `src/chirp/templating/suspense.py`, when `defer_blocks` is provided, check each block name exists in the template's block list. Log a warning for names that don't match (don't error — templates may define blocks dynamically).

**Files**: `src/chirp/templating/suspense.py`
**Acceptance**: New test in `tests/test_suspense.py` — `test_defer_blocks_warns_on_unknown_block` passes. Existing Suspense tests still pass.

### Task 2.2 — Narrow `_KidaBlockAdapter` exception handling

In `src/chirp/server/negotiation_oob.py:213-216`, replace bare `except Exception` with specific exceptions (`TemplateNotFoundError`, `TemplateSyntaxError`, `AttributeError`).

**Files**: `src/chirp/server/negotiation_oob.py:209-216`
**Acceptance**: `uv run pytest tests/test_scoped_oob.py tests/test_negotiation/ -x` passes.

### Task 2.3 — Add test for `swap_attrs` outside request context

Test that calling `swap_attrs(href)` when no request is active returns `{}` without raising.

**Files**: `tests/test_navigation_swap.py`
**Acceptance**: New test `test_swap_attrs_no_request_context` passes.

---

## Sprint 3: Integration Tests

**Goal**: Cover the new code paths with realistic app-level tests.

### Task 3.1 — Cross-shell boost redirect integration test

Create a mounted-pages app with two shell domains and verify that a boosted GET across domains triggers `hx-redirect`, while within the same domain renders content normally.

**Files**: `tests/test_handler.py` or new `tests/test_cross_shell_redirect_e2e.py`
**Acceptance**: New test passes. Tests both the redirect case and the normal rendering case.

### Task 3.2 — Streaming Alpine injection integration test

Create a test that returns `Suspense(...)` through `AlpineInject` middleware and verifies the Alpine script appears exactly once in the streamed output.

**Files**: `tests/test_streaming_html.py` or `tests/test_alpine.py`
**Acceptance**: New test passes. Alpine script appears before `</body>`, not duplicated.

### Task 3.3 — Layout OOB on Suspense stream

Create a test that verifies layout OOB blocks (sidebar, breadcrumbs) are appended to the first chunk of a Suspense streaming response during boosted navigation.

**Files**: `tests/test_scoped_oob.py`
**Acceptance**: New test passes. OOB markup appears in streamed output.

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| chirp-ui package update ships before this PR | Low | Low | Sprint 1.2 guard is no-op when import succeeds — safe either way |
| `_cross_shell_boost_redirect` fix is too broad (disables redirect for apps that need it) | Medium | Medium | Sprint 1.1 only disables when `swap_scope_map` is empty, not when metadata exists. Sprint 3.1 integration test validates both paths. |
| `defer_blocks` validation logs false warnings for dynamic templates | Low | Low | Sprint 2.1 uses warning not error; easy to suppress |
| Narrowing `_KidaBlockAdapter` exceptions misses an edge case | Low | Medium | Sprint 2.2 keeps `_log.debug` fallback; test coverage in Sprint 2 catches regressions |

---

## Success Metrics

| Metric | Current (branch) | After Sprint 1 | After Sprint 3 |
|--------|-----------------|-----------------|-----------------|
| Test failures | 26 FAILED | 0 FAILED | 0 FAILED |
| Test errors (example deps) | ~14 ERROR | ~14 ERROR (unchanged, external) | ~14 ERROR |
| Cross-shell redirect test coverage | 0 integration tests | 0 | ≥2 integration tests |
| Streaming + Alpine integration tests | 0 | 0 | ≥2 |
| `defer_blocks` validation | silent on typos | warns on unknown blocks | warns on unknown blocks |

---

## Relationship to Existing Work

- **`rfc-hierarchical-shell-swap-scopes.md`** — This epic implements the hardening needed to land the RFC's implementation. The RFC describes the design; this plan makes it mergeable.
- **`rfc-shared-store.md`** — Draft RFC for multi-consumer deferred data caching. Not blocked by this epic; can proceed after merge.
- **`rfc-unreachable-block-detection.md`** — Implemented in this branch (`rules_unreachable_blocks.py`). No additional work needed.
- **chirp-ui package** — Sprint 1.2 decouples this PR from chirp-ui's release timeline.

---

## Changelog

- **2026-04-12**: Initial draft based on deep PR analysis (16 commits, 64 files, 26 test failures identified)
