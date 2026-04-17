# Epic: Contract Tests for Framework Reliability — Close the Gaps That Shipped Bugs

**Status**: Draft
**Created**: 2026-04-17
**Target**: chirp 0.x (next reliability cut)
**Estimated Effort**: 14–22 hours
**Dependencies**: None (additive — no production code changes)
**Source**: User-cited reliability gap; recent regressions PR #90 (fail-loud OOB) and PR #87 (startup OOB validation) shipped because no end-to-end test covered the path

---

## Why This Matters

The chirp framework has solid unit-level coverage of its serialization primitives and registry data structures, but the **request → response contract** for several first-party features is exercised only indirectly. Two production bugs in the last week (PRs #87 and #90) were caused by behaviors that "should have been obvious" — the missing test was a TestClient round-trip that registers a region, makes a boosted request, and asserts the response body. We are missing that test for OOB and three sibling features (`MutationResult`, `CacheMiddleware`, `AppConfig.speculation_rules`).

**Concrete consequences:**

1. **OOB regressions ship without warning**. PRs #87 and #90 fixed bugs that no test would have caught — the registry-and-serializer unit tests in `tests/test_oob_registry.py:1` pass even when the negotiation layer silently emits empty swaps.
2. **`register_oob_region()` swap matrix is untested.** Of the six htmx swap strategies the registry accepts (`innerHTML`, `true`/`outerHTML`, `beforeend`, `afterend`, `beforebegin`, `afterbegin`), only `innerHTML` and `true` appear in tests. Optional regions (`optional=True`) have zero coverage.
3. **MutationResult never integrates with the registry under test.** `src/chirp/server/negotiation.py:261` calls `oob_registry.resolve_serialization()` but `tests/test_form_action.py` never supplies a registry — the integration is dead code from the test suite's perspective.
4. **CacheMiddleware has no request/response test.** `src/chirp/cache/middleware.py:18` has 71 lines of branching logic (GET-only, 200-only, Set-Cookie skip, streaming bypass, backend exception handling) — none of it runs through TestClient.
5. **`speculation_rules` HTML injection is untested.** The JSON snippet builder in `src/chirp/server/speculation_rules.py:1` is well unit-tested, but no test verifies the `<script type="speculationrules">` tag actually lands in `<head>` of a real response.
6. **No reproducer for the recent regressions.** A test that replays PR #90's bug against the pre-fix commit would lock in the fix forever; without it, the next refactor of the negotiation layer is one careless change away from re-introducing silent empty swaps.

**The fix:** Add ~5 new test modules (~30–40 tests) that exercise these four features end-to-end via `TestClient`, with one parametrized matrix per registration knob.

### Evidence Table

| Layer / Source | Key Finding | Proposal Impact |
|----------------|-------------|-----------------|
| Recent commits (PRs #87, #90) | Two OOB regressions shipped because no end-to-end test covered region rendering | **FIXES** — Sprint 1 adds the missing TestClient round-trip; Sprint 1 task 1.5 includes regression replay |
| `tests/test_oob_registry.py:272` | Pipeline test stops at `serialize_with_registry` — never hits HTTP layer | **FIXES** — Sprint 1 covers the layer above |
| `tests/test_negotiation/test_oob.py:13` | Tests OOB response composition but bypasses route registration / negotiation middleware ordering | **MITIGATES** — Sprint 1 covers the full middleware stack |
| `src/chirp/templating/oob_registry.py:34` | `optional: bool = False` field added; no tests reference it | **FIXES** — Sprint 2 matrix includes `optional=True` |
| `src/chirp/templating/oob_registry.py:73` | `resolve_serialization()` returns `("true", True)` for unregistered IDs | **FIXES** — Sprint 2 covers convention fallback |
| `src/chirp/server/negotiation.py:261` | MutationResult negotiation calls registry, but no test wires both together | **FIXES** — Sprint 3 test matrix includes registry-aware fragments |
| `src/chirp/cache/middleware.py:35` | CacheMiddleware `__call__` has 4 skip branches, all unverified end-to-end | **FIXES** — Sprint 4 covers all branches |
| `src/chirp/server/speculation_rules.py:115` | Snippet wrapping unit-tested; no integration test confirms it reaches the rendered page | **FIXES** — Sprint 5 covers HTML injection point |
| `tests/test_form_action.py:131` | MutationResult htmx + fragments tested without registry | **MITIGATES** — Sprint 3 closes the gap |

### Invariants

These must remain true throughout or we stop and reassess:

1. **Additive only.** Production code does not change. If a contract test fails on `main`, fix the test or open a separate bug — do not edit the framework as part of this epic.
2. **End-to-end means HTTP layer.** Every contract test boots an `App`, registers routes, and uses `chirp.testing.TestClient` to drive a real request. Tests that stop at the renderer/serializer level belong in the existing unit suites.
3. **One assertion family per test.** Tests assert on a parsed-attribute basis (`hx-swap-oob` attribute present, target ID matches), not raw HTML string equality. This protects against trivial template churn breaking the contract suite.
4. **Reproducibility.** For each of the recent regressions (PRs #87, #90), there is one named test in the new suite whose name encodes the bug it locks down (e.g. `test_missing_block_raises_block_not_found_error_pr90`).

---

## Target Architecture

### New test modules

```
tests/
  contracts/
    test_oob_pipeline_e2e.py         # NEW — Sprint 1
    test_register_oob_region_matrix.py # NEW — Sprint 2
    test_mutation_result_e2e.py      # NEW — Sprint 3
    test_cache_middleware_e2e.py     # NEW — Sprint 4
    test_speculation_rules_e2e.py    # NEW — Sprint 5
  contracts/templates/
    oob_e2e/                         # NEW — Sprint 0
      _layout.html                   # shell with title/breadcrumbs/sidebar/main regions
      page.html                      # extends layout, defines OOB blocks
      partial.html                   # secondary fragment for MutationResult
```

### Test harness shape (one consistent helper across all 5 modules)

```python
from pathlib import Path
from chirp import App
from chirp.config import AppConfig
from chirp.testing import TestClient

TEMPLATES_DIR = Path(__file__).parent / "templates" / "oob_e2e"

def _app(**overrides) -> App:
    cfg = AppConfig(template_dir=TEMPLATES_DIR, **overrides)
    return App(config=cfg)

def _boosted_get(client: TestClient, path: str):
    return client.get(path, headers={"HX-Request": "true", "HX-Boosted": "true"})
```

### Shared fixture template (`oob_e2e/_layout.html`)

Defines five distinct regions exercising every registry permutation:
- `chirpui-topbar-breadcrumbs` (innerHTML, wrap=True, optional=False)
- `chirpui-shell-title` (innerHTML, wrap=False — `<title>` self-embeds)
- `chirpui-sidebar` (true/outerHTML, wrap=True)
- `notif-feed` (beforeend, wrap=True)
- `legacy-shell` (declared but block missing — drives `optional=True` test)

This template set is the single source of truth for the OOB matrix; Sprints 1, 2, 3 all reference it.

---

## Sprint Structure

| Sprint | Focus | Effort | Risk | Ships Independently? |
|--------|-------|--------|------|----------------------|
| 0      | Shared TestClient harness + fixture templates | 2h | Low | Yes (no test failures, just new fixtures) |
| 1      | OOB pipeline end-to-end + PR #87/#90 regression replays | 4h | Medium | Yes (covers highest-value gap) |
| 2      | `register_oob_region()` swap-type matrix | 3h | Low | Yes |
| 3      | MutationResult contract tests with registry | 3h | Low | Yes |
| 4      | CacheMiddleware end-to-end | 3h | Medium | Yes |
| 5      | `AppConfig.speculation_rules` injection | 2h | Low | Yes |

**Order rationale:** Sprint 1 first — it directly addresses the cited bugs. Sprints 2–5 are independent and can ship in any order or as separate PRs.

---

## Sprint 0: Harness & Fixtures

**Goal**: Build the shared template set and TestClient helpers that Sprints 1–3 all consume.

### Task 0.1 — Add `tests/contracts/templates/oob_e2e/` fixture set

Create `_layout.html`, `page.html`, `partial.html` per the architecture section. Templates should be minimal — just enough markup to exercise each region.

**Files**: `tests/contracts/templates/oob_e2e/_layout.html`, `page.html`, `partial.html` (new)
**Acceptance**:
- `uv run pytest tests/contracts/ -k existing` still passes (no regression in existing contract suite)
- Layout template defines all five regions named in the architecture section
- `Grep -r "oob_e2e" tests/` returns at least one hit per Sprint-1 file (proves they will reuse the fixtures)

### Task 0.2 — Promote `_boosted_get` and `_app` helpers to a shared module

Place in `tests/contracts/_helpers.py` (under-bar prefix to keep pytest from treating it as a test module).

**Files**: `tests/contracts/_helpers.py` (new)
**Acceptance**: `from tests.contracts._helpers import _app, _boosted_get` resolves; helpers have docstrings explaining the htmx headers used.

---

## Sprint 1: OOB Pipeline End-to-End

**Goal**: Cover the request → registry → render → response flow that PRs #87 and #90 broke.

### Task 1.1 — Happy-path end-to-end

Register one region, return `OOB(main_fragment, oob_fragment)` from a route, assert response body contains the wrapper div with the correct `id` and `hx-swap-oob` attribute.

**Files**: `tests/contracts/test_oob_pipeline_e2e.py` (new)
**Acceptance**:
- Test parses response HTML and finds `<div id="..." hx-swap-oob="...">` for each registered region
- Both boosted and non-boosted GETs covered (boosted produces fragments; non-boosted produces full page with same OOB markers absent)

### Task 1.2 — Convention-fallback path

Return `OOB(...)` referencing a block named `sidebar_oob` with **no** registry entry; assert response targets `id="sidebar"` with default `swap=true`/`wrap=True`.

**Acceptance**: response contains `<div id="sidebar" hx-swap-oob="true">...`

### Task 1.3 — Explicit `target_id` and `wrap=False`

Register a region with explicit `target_id="custom-id"` and `wrap=False`; assert response uses the custom ID and emits the block content **without** an outer wrapper div (the block must self-include `hx-swap-oob`).

**Acceptance**: response contains `<title hx-swap-oob="true">...</title>` (or equivalent for the test fixture's wrap=False region)

### Task 1.4 — `optional=True` silent-skip

Register a region with `optional=True` against a layout that does **not** define the block; assert no error, no swap div in response, and a single WARNING-level log line.

**Acceptance**:
- Response status 200; body does not contain the optional region's `target_id`
- `caplog` captures one `WARNING` from `chirp.oob_registry` (or wherever the silent-skip logs)

### Task 1.5 — Regression replay: PR #90 (fail-loud on missing block)

Register a region with `optional=False` against a layout that does not define the block; return `OOB(...)` referencing it; assert `chirp.errors.BlockNotFoundError` is raised (via the response or a 500 with body text containing the block name).

**Files**: same module
**Acceptance**:
- `pytest.raises(BlockNotFoundError)` (or response.status == 500 with stack containing `BlockNotFoundError`)
- Test name encodes the regression: `test_missing_block_raises_block_not_found_error_pr90`
- Bonus: comment cites PR #90 with the SHA

### Task 1.6 — Regression replay: PR #87 (startup validation)

Register an `optional=False` region against a layout missing the block; call `app.check()` (or whatever the startup validation entry point is); assert it returns an ERROR-severity issue under category `oob_registry`.

**Acceptance**:
- `result = app.check()`; `result.has_errors()` is True; matching issue has `category == "oob_registry"` and `severity == Severity.ERROR`
- Same with `optional=True` returns severity `WARNING` instead of `ERROR`
- Test name: `test_orphaned_oob_registration_flagged_at_startup_pr87`

---

## Sprint 2: `register_oob_region()` Matrix

**Goal**: Cover every swap type, fallback path, and registration error case.

### Task 2.1 — Parametrized swap-type matrix

`@pytest.mark.parametrize("swap", ["innerHTML", "true", "beforeend", "afterend", "beforebegin", "afterbegin"])` — for each, register a region, render an OOB response, assert the wrapper div carries `hx-swap-oob="<swap>"`.

**Files**: `tests/contracts/test_register_oob_region_matrix.py` (new)
**Acceptance**: All 6 swap variants pass; one assertion per variant; failure output names which swap broke

### Task 2.2 — Invalid swap rejected

`pytest.raises(ValueError)` when `register_oob_region(..., swap="garbage")` is called.

**Acceptance**: error message names the invalid value

### Task 2.3 — Freeze guard

Register one region, call `app.run()` or trigger freeze, assert subsequent `register_oob_region()` raises `RuntimeError` with the expected message.

**Acceptance**: `RuntimeError` raised; message contains "frozen" or "after app has started"

### Task 2.4 — Duplicate registration overwrites (or rejects — verify intent)

Register the same block name twice with different configs. **First**, document current behavior via the existing source (`oob_registry.py:54` overwrites silently). Then test that behavior. If the intent is to reject duplicates, this test will fail and surface that intent — prompting either a code change in a separate PR or a tightened test.

**Acceptance**: test documents the actual current behavior with a clear comment ("currently overwrites silently — see oob_registry.py:54")

---

## Sprint 3: MutationResult Contract Tests

**Goal**: Cover the registry-aware path through `MutationResult` / `FormAction`.

### Task 3.1 — htmx POST + fragments resolve via registry

Register an OOB region; route returns `MutationResult("/ok", Fragment("partial.html", "block"))`; POST with `HX-Request: true`; assert response body contains the fragment wrapped per registry config (not default `outerHTML`).

**Files**: `tests/contracts/test_mutation_result_e2e.py` (new)
**Acceptance**:
- Response contains fragment with the registry-configured `hx-swap-oob` attribute (e.g. `innerHTML` if registered as such, **not** the default `true`)
- Test fails on a hypothetical regression where registry is bypassed (e.g. swap defaults to `true`)

### Task 3.2 — htmx POST + no fragments → HX-Redirect header

Route returns `MutationResult("/done")`; POST with htmx; assert `HX-Redirect: /done` header and 200 status.

**Acceptance**: header present with exact value; no `Location` header

### Task 3.3 — non-htmx POST → 303 Location

Same route, no htmx headers; assert 303 status with `Location: /done`.

### Task 3.4 — HX-Trigger header

`MutationResult("/x", trigger="event-name")` — assert `HX-Trigger: event-name` header in htmx response.

### Task 3.5 — Explicit `Fragment.swap` overrides registry

Register region with `swap="innerHTML"`; return `MutationResult(..., Fragment(..., swap="beforeend"))`; assert response uses `beforeend` (explicit beats registry).

**Acceptance**: response contains `hx-swap-oob="beforeend"` for the explicit fragment

---

## Sprint 4: CacheMiddleware End-to-End

**Goal**: Cover every branch in `src/chirp/cache/middleware.py:35`.

### Task 4.1 — Cache miss then hit

Build app with `cache_middleware_enabled=True` and an in-memory backend; GET the same URL twice; assert second response served from cache (use a route counter that increments on each handler invocation; assert counter == 1 after two requests).

**Files**: `tests/contracts/test_cache_middleware_e2e.py` (new)
**Acceptance**: handler invocation count == 1 after two GETs; both responses have status 200 and equal bodies

### Task 4.2 — Non-GET bypass

POST to the same URL twice; assert handler runs both times (counter == 2).

### Task 4.3 — Set-Cookie skip

Route returns a `Response` with `Set-Cookie` header; GET twice; assert handler runs both times.

### Task 4.4 — Non-200 skip

Route returns 404; GET twice; assert handler runs both times.

### Task 4.5 — Streaming/SSE bypass

Route returns `EventStream(...)`; GET twice; assert handler runs both times (streaming responses are never cached per `middleware.py:59`).

### Task 4.6 — TTL expiry

Use a backend with mockable time or a `ttl=1` setting; GET, advance clock past TTL, GET again; assert handler runs both times.

**Acceptance**: counter == 2; if backend doesn't support time mocking, use `asyncio.sleep(1.1)` (mark test slow)

### Task 4.7 — Backend get() exception → request still served

Inject a backend whose `get()` raises; GET; assert request returns the handler's response normally and a `WARNING` log line is captured.

**Acceptance**: response status 200; `caplog` captures one warning from `chirp.cache`

---

## Sprint 5: `AppConfig.speculation_rules` Injection

**Goal**: Verify the speculation-rules snippet reaches the rendered HTML.

### Task 5.1 — Snippet present when enabled

Build app with `speculation_rules=True`; GET a full page; assert response body contains `<script type="speculationrules"` and `data-chirp="speculation-rules"`.

**Files**: `tests/contracts/test_speculation_rules_e2e.py` (new)
**Acceptance**: both substrings present; snippet appears inside `<head>...</head>`

### Task 5.2 — Snippet absent when disabled

Same test with `speculation_rules=False`; assert neither substring appears.

### Task 5.3 — Mode parametrization

`@pytest.mark.parametrize("mode", ["conservative", "moderate", "eager"])` — each produces a snippet whose JSON content differs (assert on the embedded JSON's `prefetch`/`prerender` keys per mode).

### Task 5.4 — POST and SSE routes excluded from rules

App with one GET, one POST, one SSE route; assert the JSON in the snippet contains the GET path but not the POST or SSE paths.

### Task 5.5 — Snippet excluded from fragment responses

Boosted GET (htmx fragment) of a page; assert speculation-rules snippet **not** included (only full-page navigations need it).

**Acceptance**: response status 200, body does not contain `type="speculationrules"`

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Tests assert on raw HTML string equality and break on harmless template churn | Medium | Medium | Invariant 3 mandates parsed-attribute assertions; reviewer enforces in PR |
| Shared `oob_e2e/` fixture set drifts from real layouts (e.g. `chirp_ui`'s actual block names) | Medium | Low | Sprint 0 fixture templates are minimal and self-contained — no dependency on `chirp_ui` |
| CacheMiddleware tests share global state (process-wide cache) and interfere | Low | Medium | Each test instantiates a fresh `App` with a fresh in-memory backend; no module-level fixtures |
| `optional=True` silent-skip log assertion is fragile (depends on logger name) | Low | Low | Sprint 1 task 1.4 uses `caplog.at_level("WARNING", logger="chirp...")` and tests the substring of the message, not the full string |
| Regression replay tests (PR #87, #90) drift if the fix is later refactored | Low | Medium | Comment in test cites PR + SHA so future maintainers can re-validate against the original bug description |
| Sprint 1 reveals a real production bug (test fails on `main`) | Low | High | Stop the epic, file a separate bug PR, then resume — Invariant 1 forbids fixing in the same PR |

---

## Success Metrics

| Metric | Current | After Sprint 1 | After Sprint 5 |
|--------|---------|----------------|----------------|
| End-to-end OOB tests using TestClient | 0 | 6 | 6 |
| `register_oob_region()` swap variants tested | 2 of 6 | 2 of 6 | 6 of 6 |
| MutationResult tests with registry wired in | 0 | 0 | 5 |
| CacheMiddleware request/response tests | 0 | 0 | 7 |
| `speculation_rules` integration tests | 0 | 0 | 5 |
| PR #87 + PR #90 regression replays | 0 | 2 | 2 |
| Total new tests | 0 | ~8 | ~30–35 |

**Coverage targets (`uv run pytest --cov`):**
- `src/chirp/templating/oob_registry.py` — currently ~75% line coverage; target ≥95%
- `src/chirp/cache/middleware.py` — currently 0% (only backend tested); target ≥90%
- `src/chirp/server/speculation_rules.py` — currently ~80%; target ≥95%

---

## Relationship to Existing Work

- **PR #87 (4e888da)** — *prerequisite for Sprint 1.6*. The startup validation behavior this epic locks down was added in #87; without that fix shipped, Task 1.6 can't pass.
- **PR #90 (fd53ff8)** — *prerequisite for Sprint 1.5*. The fail-loud `BlockNotFoundError` introduced in #90 is what Task 1.5 asserts on.
- **`tests/test_oob_registry.py`** — *parallel*. The existing unit suite covers the data structure; this epic covers the HTTP contract above it. Both should remain.
- **`tests/test_form_action.py`** — *parallel*. Covers MutationResult construction and basic htmx negotiation; this epic adds the registry-integration cases the existing suite skips.
- **`docs/guides/oob-registry.md`** — *informative*. Sprint 1 task acceptance criteria should match the contract this guide documents; if they diverge, file a bug.

---

## Changelog

- **2026-04-17** — Initial draft.
