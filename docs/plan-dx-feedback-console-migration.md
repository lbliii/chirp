# Epic: Refactor-Friendly Chirp — DX Feedback from Console Migration

**Status**: Completed
**Created**: 2026-04-23
**Target**: chirp 0.6
**Estimated Effort**: 18–26 h
**Dependencies**: kida-templates (upstream, out of scope for this plan)
**Source**: User feedback from migrating dashboard → new console architecture (5 friction points observed during large-scale IA refactor)

**Completed**: 2026-05-03
**Verification**:

- `src/chirp/app/url_for.py`
- `src/chirp/app/mount.py`
- `src/chirp/contracts/rules_page_handlers.py`
- `src/chirp/contracts/rules_route_names.py`
- `tests/test_url_for.py`
- `tests/test_mount_app.py`
- `tests/test_page_handler_check.py`
- `tests/test_page_error.py`
- `docs/routing/mounting.md`

---

## Current Status

This plan is now a historical implementation record. The in-repo work landed
for Chirp 0.6: named routes, `url_for`, page-handler contract checks, guided
`Page(...)` errors, `mount_app`, and example migration coverage all exist in
the current tree.

The remaining dependency-thread is external: Kida relative include behavior is
tracked outside this repository in
[lbliii/kida#126](https://github.com/lbliii/kida/issues/126) and should not be
treated as an open Chirp implementation task.

---

## Why This Mattered

A user completing a large IA refactor of a Chirp app surfaced five DX friction points where the framework forces manual fan-out work or fails late instead of early. The common thread: **Chirp has good contracts but leaky identifiers** — hardcoded URL strings, template paths, and handler names that don't participate in the framework's existing validation story.

The fix is to route those identifiers through Chirp's existing registries (route name → URL, page.py → handler check, App → mountable unit) so refactors propagate automatically and mistakes fail at `app.check()` instead of request time.

### Consequences observed

1. **85 hardcoded `hx-get`/`hx-post`/etc. URLs** across 24 template files in-repo (examples only; real apps carry more). IA changes become a manual find-and-replace across the codebase.
2. **19 page.py files in-repo** with no startup validation that they expose a valid handler. Misspelled handlers 500 at request time instead of failing `app.check()`.
3. **`Page.__init__` requires `block_name` positional-only** (`src/chirp/templating/returns.py:205`); users reach for `Page` when they mean `Template`, get a `TypeError` with no hint toward the right type.
4. **`app.mount(prefix, plugin)`** only accepts objects with `.register()` (`src/chirp/app/__init__.py` ~L400); users trying to compose two full Chirp apps during a migration get `ConfigurationError` with no guidance on the intended pattern.
5. **Kida `{% include %}` uses absolute paths** — every file move breaks every include. Upstream concern (external dep `kida-templates>=0.7.0`); tracked separately.

### The fix

Introduce named routes + `url_for`, promote page-handler discovery warnings into contract checks, tighten the `Page` vs `Template` error ergonomics, and ship a `mount_app` adapter that wraps a sub-app as a plugin. Kida relative includes remain upstream.

### Evidence Table

| Source | Key Finding | Proposal Impact |
|--------|-------------|-----------------|
| `src/chirp/app/registry.py:29,184,301` | Routes carry a `name: str \| None` field; always `None` at page discovery | **FIXES** — Sprint 2 populates `name` from page path, adds `url_for` resolver |
| `src/chirp/server/fragment_dispatch.py:55` + `src/chirp/app/compiler.py:349` | `fragment_url` already registered as template global via `setdefault` | **FIXES** — Sprint 2 follows the same pattern for `url_for` |
| `src/chirp/pages/discovery.py:555-570` | Discovery logs WARNING for handler-shaped functions; never surfaces to `app.check()` | **FIXES** — Sprint 1 promotes to `CheckResult` issues via new `page_handlers` category |
| `src/chirp/templating/returns.py:205-213` | `Page.__init__(template_name, block_name, /, ...)` — positional-only, no error-message hint toward `Template` | **FIXES** — Sprint 3 replaces generic `TypeError` with a guided message |
| `src/chirp/app/__init__.py:~400` | `mount` rejects non-plugin objects with `ConfigurationError` | **MITIGATES** — Sprint 4 adds `mount_app(prefix, other_app)` adapter that wraps `App` as a plugin |
| External dep `kida-templates>=0.7.0` | No relative-include syntax today | **UNRELATED** — tracked as upstream issue, not this plan |

### Invariants

These must remain true throughout or we stop and reassess:

1. **`app.check()` stays issue-first, never raises during `register()`.** New page-handler check must emit `ContractIssue` objects, not raise — so plugins that register broken page trees don't explode at mount time.
2. **Template globals namespace stays setdefault-respecting.** `url_for` must use the same `setdefault` pattern as `fragment_url` (`src/chirp/app/compiler.py:349`) so apps that already defined `url_for` aren't silently clobbered.
3. **Backwards compat for unnamed routes.** Existing `app.route(...)` calls without a `name` keep working; `url_for` raises `LookupError` with a helpful message when called on an unknown name rather than returning an empty string.
4. **No new runtime cost on the request path.** Named-route lookup table is built once at freeze, not per-request.

---

## Target Architecture

```
Route(name: str | None, path: str, handler, methods, ...)
       │
       ├── registered explicitly:  @app.route("/x", name="x.view")
       └── registered via pages:   pages/x/page.py  →  name derived as "x" (file-path policy)
       
Registry._routes_by_name: FrozenMapping[str, Route]  ← built at freeze
       │
       ▼
url_for(name, **path_params, **query) -> str
       │
       ├── template global (setdefault)       → {{ url_for("x.view", id=42) }}
       └── public api on App                  → app.url_for("x.view", id=42)

app.check() additions:
  - page_handlers:  page.py without valid handler → ERROR
  - page_handlers:  handler-shaped function with typo → WARNING (same as current log)

app.mount_app(prefix, sub_app) -> None  ← adapter
  wraps sub_app as a Plugin-shaped object and delegates to existing mount()

Page(template_name, block_name)  ← unchanged API
  improved TypeError message when block_name missing, pointing at Template()
```

---

## Sprint Structure

| Sprint | Focus | Effort | Risk | Ships Independently? |
|--------|-------|--------|------|---------------------|
| 0 | Design: named-route scheme, `url_for` signature, mount_app semantics | 2 h | Low | Yes (RFC only) |
| 1 | `app.check()` page-handler validation | 2 h | Low | Yes |
| 2 | Named routes + `url_for` template global | 6–8 h | Medium | Yes |
| 3 | `Page` error message + docs decision tree | 2 h | Low | Yes |
| 4 | `mount_app` adapter for sub-App composition | 3–4 h | Medium | Yes |
| 5 | Migrate in-repo examples/tests to `url_for` + file upstream Kida relative-include issue | 3–4 h | Low | Yes |

---

## Sprint 0: Design & Validate

**Goal**: Resolve the two open design questions before writing code. Capture decisions in `docs/rfcs/` so reviewers can push back on the shape, not the implementation.

### Task 0.1 — Named-route naming policy

Write `docs/rfcs/named-routes.md` answering:

- **Explicit naming**: `@app.route("/x", name="x.view")` — how does this interact with existing `register_fragment` / fragment-aware routes? (fragment variants should share a base name or have their own?)
- **Page-based naming**: what is the default derived name for `pages/contacts/{contact_id}/page.py`? Options:
  - (A) Dotted from path: `contacts.contact_id` (needs pruning for dynamic segments)
  - (B) Underscored with method suffix: `contacts__contact_id__get`
  - (C) Opt-in only: leave `name=None` unless user sets a module-level `name = "..."`
  - Recommend (A) with override via module-level `name` attr; document collision behavior.
- **Duplicate names**: hard error at freeze or last-wins? Recommend hard error (fail `app.check()` with a `route_names` category).

**Acceptance**: RFC committed; decision recorded for (A/B/C); collision policy stated in one sentence.

### Task 0.2 — `url_for` signature & path-param binding

Decide the signature and binding rules. Propose:

```python
def url_for(name: str, /, **params: Any) -> str:
    # 1. look up Route by name in registry._routes_by_name
    # 2. if route has path params ({contact_id}), consume matching kwargs
    # 3. any remaining kwargs → urlencoded query string
    # 4. unknown name → LookupError("No route named 'x.view'. Known: [...]")
    # 5. missing path param → KeyError with list of required params
```

Decide:
- Should `url_for` quote path params? (yes — use `urllib.parse.quote`, `safe=""`)
- Should it support absolute URLs (scheme/host) via a kwarg? Recommend **no** in v1 — keep it local.
- Should it respect app `root_path` / prefix? Recommend **yes** — read from `AppConfig` at freeze time.

**Acceptance**: RFC committed; signature nailed; 4 worked examples in the RFC including a page-based route with a path param.

### Task 0.3 — `mount_app` semantics

Decide what "mounting a sub-app" means when the sub-app also has its own `app.check()`, freeze, middleware stack:

- Recommend: `mount_app(prefix, sub_app)` is sugar that calls `sub_app.freeze()` eagerly, extracts its route table + template globals + middleware, and registers them on the parent at `prefix`. Sub-app's own runtime loop does not run.
- Alternative: true ASGI composition (sub-app stays a full app behind a prefix). Rejected for v1 — splits `app.check()` and doubles middleware evaluation.

**Acceptance**: RFC committed; semantics stated; one explicit non-goal ("not full ASGI composition") documented.

---

## Sprint 1: Page-Handler Contract Check

**Goal**: Startup fails fast when a `page.py` doesn't expose a recognizable handler, replacing the existing runtime 500.

### Task 1.1 — Add `page_handlers` contract check category

Promote the warning at `src/chirp/pages/discovery.py:555-570` into a check result.

- Record handler-discovery results on the discovered `PageRoute` (e.g., add `handler_warnings: tuple[str, ...] = ()` to `PageRoute` — or collect them on the mutable state during page mount).
- Register a built-in contract check that iterates discovered `PageRoute`s and emits:
  - `Severity.ERROR` if no handler was found (page.py has no `get`/`post`/.../`handler`)
  - `Severity.WARNING` for each handler-shaped typo (current log line).
- Category string: `"page_handlers"` — eligible for `override_contract_severity()`.

**Files**: `src/chirp/pages/discovery.py`, `src/chirp/app/check.py` (or wherever built-in checks live).
**Acceptance**:
- `rg 'page_handlers' src/` returns the new check and nothing else.
- New test `tests/test_page_handler_check.py` mounts a `pages/` tree with a `page.py` containing only `def handle(...)` and asserts `app.check()` returns an ERROR issue with category `page_handlers`.
- Existing warning log line for typos still fires (dual-surface during transition: log + check issue). Regression check: `rg 'looks like a handler' src/chirp/pages/discovery.py` still finds the warning call.

### Task 1.2 — Document the new check

Add a row to the `app.check()` categories table in `docs/guides/` (or equivalent) documenting `page_handlers` + severity override example.

**Acceptance**: `rg 'page_handlers' docs/` finds the documentation entry.

---

## Sprint 2: Named Routes + `url_for`

**Goal**: Eliminate hardcoded URL strings in templates. IA refactors propagate through the route name registry instead of find-and-replace.

### Task 2.1 — Populate `Route.name` at page discovery

Per Sprint 0's decision (assume (A) — dotted path names with module-level override):

- In `src/chirp/pages/discovery.py:585` where `name=None` is currently passed, compute the default name from the URL path (dynamic segments stripped or keyed).
- Check for a module-level `name = "..."` attribute on the page module — if present, use it verbatim (opt-in override).

**Files**: `src/chirp/pages/discovery.py`.
**Acceptance**:
- `tests/test_page_discovery_names.py` asserts `pages/contacts/page.py` → name `"contacts"`; `pages/contacts/{contact_id}/page.py` → name `"contacts.contact_id"` (or whatever Sprint 0 chose); module-level override beats the default.
- Full test suite passes.

### Task 2.2 — Build `_routes_by_name` at freeze

In the App registry, build a `MappingProxyType` keyed by name, built once at `freeze()`:

- Detect duplicate names; emit `Severity.ERROR` via a new `route_names` contract check.
- Expose `app.url_for(name, **params)` on the public App API.

**Files**: `src/chirp/app/registry.py`, `src/chirp/app/__init__.py`, `src/chirp/app/check.py`.
**Acceptance**:
- `app.url_for("x", id=42)` returns the bound URL; `app.url_for("nope")` raises `LookupError` whose message lists known names.
- Duplicate names fail `app.check()` with category `route_names`.
- Test: `tests/test_url_for.py` covers static route, path-param route, query-param pass-through, unknown name, duplicate name.

### Task 2.3 — Register `url_for` as a template global

Follow the `fragment_url` precedent at `src/chirp/app/compiler.py:349`:

```python
self._mutable.template_globals.setdefault("url_for", app.url_for)
```

**Files**: `src/chirp/app/compiler.py`.
**Acceptance**:
- `{{ url_for("contacts.contact_id", contact_id=42) }}` renders `/contacts/42` in a rendered template.
- If a user has already registered `url_for` as a template global, theirs wins (setdefault semantics). Regression test asserts this.

### Task 2.4 — Example migration in one bundled example

Pick one example (recommend `examples/chirpui/contacts_shell`) and migrate every hardcoded `hx-*` URL to `{{ url_for(...) }}` as a demonstration.

**Acceptance**:
- `rg 'hx-(get|post|put|delete|patch)="/contacts' examples/chirpui/contacts_shell/` returns zero hits (every URL now goes through `url_for`).
- Example still runs end-to-end (manual smoke test noted in PR).

---

## Sprint 3: Page / Template Error Ergonomics

**Goal**: When a user writes `return Page("page.html", **ctx)` meaning `return Template(...)`, the error message points them to the right type instead of surfacing a generic `TypeError`.

### Task 3.1 — Replace generic TypeError on `Page(...)` misuse

Options:
- (A) Keep the positional-only signature, override `__init__` to raise a guided error when called with one positional arg.
- (B) Add a separate classmethod constructor.

Recommend (A). Example target message:

```
Page requires a block name: Page("page.html", "content_block").
For a plain full-page render without htmx negotiation, use Template("page.html", **ctx).
See docs/guides/returns.md for the decision tree.
```

**Files**: `src/chirp/templating/returns.py`.
**Acceptance**:
- `tests/test_page_error.py` asserts the error message string contains both `Page("page.html", "..."` and `Template(`.
- Regression: existing valid usage `Page("page.html", "content", **ctx)` still works unchanged.

### Task 3.2 — Docs decision tree for return types

Add or update `docs/guides/returns.md` with a decision tree at the top:

- "Full page, no htmx awareness?" → `Template`
- "Full page that should be a fragment for htmx and a page for browsers?" → `Page`
- "Just a named block?" → `Fragment`
- "Multiple OOB targets?" → `OOB`

**Acceptance**: `rg 'decision tree' docs/guides/returns.md` finds the section heading.

---

## Sprint 4: `mount_app` Adapter

**Goal**: Allow composing two Chirp Apps on the same port during migrations without forcing users to learn the plugin protocol.

### Task 4.1 — Implement `App.mount_app(prefix, sub_app)`

Per Sprint 0 semantics — eager-freeze + hoist routes/globals/middleware:

- Freeze `sub_app`.
- Re-register its routes on `self` under `prefix`.
- Merge template globals via `setdefault` (parent wins on conflict).
- Append middleware in sub-app order.
- Raise `ConfigurationError` with a useful message if `sub_app` is already frozen by a different parent (state ownership would get tangled).

**Files**: `src/chirp/app/__init__.py`.
**Acceptance**:
- New test `tests/test_mount_app.py` covers: two apps with disjoint routes mount cleanly; duplicate prefix conflict errors; sub-app's middleware runs for requests hitting the prefix.
- `rg 'def mount_app' src/` finds exactly one definition.

### Task 4.2 — Document `mount_app` vs `mount`

Extend the plugin / mount docs with a section explaining:
- `mount(prefix, plugin)` — for reusable packaged pieces (`register(app, prefix)` contract).
- `mount_app(prefix, sub_app)` — for composing two full apps during transitional phases.

**Acceptance**: `rg 'mount_app' docs/` finds a side-by-side comparison section.

---

## Sprint 5: Migration & Upstream Follow-through

**Goal**: Migrate in-repo examples to `url_for` and file the upstream Kida issue so the last piece of feedback isn't dropped.

### Task 5.1 — Sweep in-repo examples

Replace hardcoded `hx-*` URLs with `{{ url_for(...) }}` across examples + tests where the route names are now available.

**Acceptance**:
- `rg 'hx-(get|post|put|delete|patch)="/' examples/` count drops from 85 to ≤10 (only the ones where dynamic names don't make sense).
- All example app tests still pass.

### Task 5.2 — File upstream Kida relative-include issue

Draft a feature request for `kida-templates` proposing `{% include "./x.html" %}` resolving relative to the current template's directory, referencing the user's use case (file moves breaking every include).

**Acceptance**: Issue filed; link captured in `docs/release-rough-edges.md` under a "tracked upstream" section.

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Route-name collisions in large apps once defaults populate | Medium | High | Sprint 0 picks a naming scheme that minimizes collisions (Task 0.1); Sprint 2 adds a hard-error `route_names` contract check (Task 2.2) |
| `url_for` path-param binding semantics differ from user expectations (query vs path) | Medium | Medium | Sprint 0 Task 0.2 nails rules with 4 worked examples before any code is written |
| `mount_app` freeze timing surprises — user mounts sub-app mid-setup | Medium | High | Sprint 0 Task 0.3 picks eager-freeze semantics with a clear error when the sub-app is already frozen elsewhere (Task 4.1) |
| Users rely on the generic `TypeError` from `Page(...)` in their own tests | Low | Low | Task 3.1 keeps the exception type as `TypeError`, only changes the message |
| `url_for` template global clobbers a user's existing definition | Low | Medium | Sprint 2 Task 2.3 uses `setdefault` pattern (mirrors `fragment_url`); regression test asserts user wins |
| Sprint 2 performs extra work at freeze, slows boot | Low | Low | `_routes_by_name` is a single dict comprehension; benchmark only if `app.check()` timing regresses >5% |

---

## Success Metrics

| Metric | Current | After Sprint 2 | After Final Sprint |
|--------|---------|----------------|-------------------|
| Hardcoded `hx-*` URLs in in-repo templates | 85 | 85 (urls available but not swept) | ≤10 |
| `page.py` with missing/typo'd handler | Silent 500 at request time | Fails `app.check()` (already shipped in Sprint 1) | Same |
| Chirp APIs that accept a sub-App | 0 | 0 | 1 (`mount_app`) |
| `Page(...)` TypeError includes pointer to `Template(...)` | No | No | Yes |
| Upstream Kida relative-include issue filed | No | No | Yes |

---

## Relationship to Existing Work

- **`fragment_url` template global** (`src/chirp/app/compiler.py:349`) — `url_for` in Sprint 2 follows the exact same registration pattern; treat `fragment_url` as the reference implementation.
- **`register_fragment` / fragment-aware routes** — Sprint 0 Task 0.1 must decide how named routes interact with fragment variants. If a route `x.view` has a fragment variant, is there a separate name? Must not break existing fragment dispatch.
- **`app.check()` contract system** (`docs/guides/oob-registry.md`, `chirp.ContractCheck`) — Sprint 1 and Sprint 2 add new categories (`page_handlers`, `route_names`) that hook into the existing `override_contract_severity` machinery. No new infra.
- **Kida `kida-templates>=0.7.0`** — relative-include feature (item #1 of original feedback) is upstream. Sprint 5 Task 5.2 files the issue; not implemented here.

---

## Changelog

- **2026-04-23** — Initial draft from user feedback on console-migration DX friction.
