# Epic: Scaffold Modernization — Teach the Current Chirp on `chirp new`

**Status**: Sprint 6 complete — epic done. Snapshot + contract + runtime tests lock in the modernization. 46 new tests in `tests/cli/`: 5 contract-freeze (all modes × plain v2), 39 grep-invariant patterns, 2 runtime smoke. Every scaffold pattern and every contract invariant is now guarded.
**Created**: 2026-04-20
**Target**: 0.4.x patch line (no version bump required)
**Estimated Effort**: 10–14h
**Dependencies**: None (purely additive/replace inside `src/chirp/cli/templates/`)
**Source**: Verification audit of `src/chirp/cli/templates/` against current examples and `CLAUDE.md` (lbliii/verify-scaffolds branch).

---

## Why This Matters

`chirp new` generates projects that use pre-0.4 patterns — it teaches a framework that no longer matches the one we ship.

1. **Users start 2 minor versions behind.** `scaffold.py:15,19` pins `bengal-chirp>=0.2.0` and `chirp-ui>=0.2.0`. Current: 0.4.0 and 0.3.0. Every `uv add` or `pip install` on a freshly scaffolded project resolves to code from two minor releases ago.
2. **Zero scaffolds showcase the headline intent types.** `Page`, `Suspense`, `OOB`, `ValidationError`, `FormAction` — none appear in any scaffold output despite being the central selling point of the framework per `CLAUDE.md`. A new user reading their generated `app.py` would not know these exist.
3. **V2 handler/template conventions diverge from every current example.** Scaffold pages use `async def handler():` (v2.py:281,308,368) and `{% extends "_layout.html" %}{% block content %}` (v2.py:286,295,314,334,373,383). Every example in `examples/chirpui/**/page.py` uses `def get(request)` / `async def post(request)` and the `page_root → page_root_inner → page_content` composition block structure. A user who scaffolds then reads an example will see two different Chirps.
4. **`full.py` is mostly dead code with divergent behavior.** 3 of 5 re-exported constants are unused by `_new.py`; the 2 that are used (`TEST_APP_PY`, `STYLE_CSS`) come from a file whose `app.py` constant targets a different framework shape than the SSE scaffold it serves. The test (`TEST_APP_PY:73-75`) defines its own `@app.route("/")` returning a bare string `"Hello, world!"`, which only passes because the assertion checks `status == 200` and nothing about body.
5. **Dead/cross-wired imports.** `V2_APP_PY` imports `EventStream, Fragment` but neither is used in that variant (only in `V2_APP_CHIRPUI_PY`, v2.py:9-10). `V2_APP_CHIRPUI_PY` has a bare `import chirp_ui` (v2.py:103) — unused; registration is via top-level `use_chirp_ui(app)`.

Bring scaffold outputs back in sync with the framework they ship from.

### Evidence

| Layer/Source | Key Finding | Proposal Impact |
|-------------|-------------|-----------------|
| `scaffold.py:15` — `bengal-chirp>=0.2.0` vs root `version="0.4.0"` | Stale version floor | **FIXES** (Sprint 1) |
| `scaffold.py:19` — `chirp-ui>=0.2.0` vs root `ui=["chirp-ui>=0.3.0"]` | Stale version floor | **FIXES** (Sprint 1) |
| `v2.py:281,308,368` — `async def handler()` in all 3 page files | Non-canonical handler names | **FIXES** (Sprint 2) |
| `v2.py:282,310,369` — `Template("page.html")` returns | Missing `Page` auto fragment/full | **FIXES** (Sprint 2) |
| `v2.py:69` — `Redirect("/login?error=1")` on bad creds; `V2_LOGIN_HTML` reads error via query param | Diverges from `kanban_shell/pages/login/page.py:41-48` which returns `Page(..., error="...")` | **FIXES** (Sprint 3) |
| `v2.py:286,295,314,334,373,383` — `{% extends %}{% block content %}` | Missing composition (`page_root`/`page_content`) | **FIXES** (Sprint 4) |
| `v2.py:9-10` — unused `EventStream, Fragment` in non-UI app | Dead imports | **FIXES** (Sprint 1) |
| `v2.py:103` — bare `import chirp_ui` | Dead import | **FIXES** (Sprint 1) |
| `full.py` + `templates/__init__.py:6-12` — 3/5 exports unused | Dead-code surface area | **FIXES** (Sprint 1) |
| No scaffold uses `Page`, `Suspense`, `OOB`, `ValidationError`, `FormAction` | Zero showcase of intent types | **FIXES** (Sprint 5) |

### Invariants

These must remain true throughout or we stop and reassess:

1. **Scaffolds pass `app.check()` on startup.** Run via `chirp new /tmp/foo --sse && cd /tmp/foo && uv run python -c "from app import app; app.freeze()"` — should exit 0 with no ERROR issues.
2. **Generated projects are test-runnable out of the box.** `uv run pytest` in a freshly scaffolded project must pass without edits.
3. **Every scaffold pattern is grep-equivalent to at least one file under `examples/`.** If a scaffold teaches it, a current example must use it. No scaffold-only idioms.

---

## Target Architecture

Scaffold outputs by mode, after this epic:

```
minimal/   → Bare Template return, no middleware. Teaches: App, route, Template.
            (Pedagogical entry point — resist feature creep.)

sse/       → Template + EventStream + Fragment + Page for the index.
            Imports top-level from chirp (not chirp.streaming).
            Teaches: intent types, SSE, page.html blocks.

shell/     → Persistent shell layout, filesystem routing, _context.py.
            Pages use def get(request) + Page("...", "page_content", page_block_name="page_root").
            Teaches: mount_pages, composition, shell layout.

v2/        → Auth + CSRF + sessions + login + dashboard (current default).
            Login uses ValidationError on bad creds (not Redirect).
            All pages: def get(request)/async def post(request), return Page(...).
            Templates: page_root → page_root_inner → page_content blocks (no extends).
            Teaches: middleware stack, auth, intent-typed form errors.

v2/+ui     → Same as v2 with chirpui macros. use_chirp_ui(app) only (no bare import).

(new) oob/ → Minimal OOB demo: POST handler returning OOB(main_fragment, *oobs).
            Teaches: multi-target swap, register_oob_region.
            OPTIONAL — only if Sprint 0 decides scaffold count should grow.
```

Module layout:

- `templates/full.py` → **deleted or retired to a `_legacy.py`**. Its two consumed constants migrate to `sse.py` (where they belong) and `scaffold.py`.
- `templates/__init__.py` stops re-exporting unused names.
- `templates/scaffold.py` pins current versions; adds a snapshot of extras used by each mode.

---

## Sprint Structure

| Sprint | Focus | Effort | Risk | Ships Independently? |
|--------|-------|--------|------|---------------------|
| 0 | Design decisions: login flow, scaffold count, `full.py` fate | 1h | Low | Yes (RFC only) |
| 1 | Version bumps + dead-code cleanup + dead imports | 2h | Low | Yes |
| 2 | V2 handler conversion (`handler` → `get`/`post`, `Template` → `Page`) | 2h | Medium | Yes |
| 3 | V2 login → `ValidationError` intent type | 1.5h | Medium | Yes |
| 4 | V2 templates → composition block structure | 2h | Medium | Yes |
| 5 | Showcase additions: `Suspense`/`OOB` demo (optional new mode) | 2h | Medium | Yes (can be skipped) |
| 6 | Snapshot tests so `app.check()` + grep invariants stay green | 2h | Low | Yes |

---

## Sprint 0: Design & Validate — COMPLETE (2026-04-20)

**Goal**: Pick the canonical choices before touching any scaffold string.

### Task 0.1 — Login flow canonical pattern ✅

**Decision: `Page(..., error="...")`, NOT `ValidationError`.**

Grep result: `ValidationError` is the convention for generic form POSTs (signup, contacts, wizard, todo, kanban actions, survey, accessibility, upload — 10+ examples). **But** the only filesystem-routed login page in the codebase — `examples/chirpui/kanban_shell/pages/login/page.py:41-48` — returns `Page("login/page.html", "page_content", page_block_name="page_root", error="Invalid username or password", ...)` on bad creds, **not** `ValidationError`.

Scaffold invariant 3 requires every emitted pattern to be grep-equivalent to an example. Using `ValidationError` in the scaffolded login would violate that invariant — there's no `login/page.py` in any example that does it that way. Mirror `kanban_shell` exactly.

> **Sprint 3 revision**: rename from "→ `ValidationError`" to "→ `Page(..., error=...)` mirroring kanban_shell". See Sprint 3 changes below.

**Citation**: `examples/chirpui/kanban_shell/pages/login/page.py:41-48`

### Task 0.2 — `full.py` fate ✅

**Decision: Delete `APP_PY`, `BASE_HTML`, `INDEX_HTML` (true dead code). Move `TEST_APP_PY` + `STYLE_CSS` into `sse.py` (only consumer). Delete `full.py`. Update `__init__.py` and `_templates.py` re-export lists. Keep the `_templates.py` backward-compat shim itself.**

Evidence gathered:
- `src/chirp/cli/_new.py` imports none of `APP_PY`, `BASE_HTML`, `INDEX_HTML`. All three are truly unused internally.
- `src/chirp/cli/_templates.py` is a "backward-compatible shim" per its docstring — re-exports everything from `chirp.cli.templates`. `tests/test_cli_new.py:10-15` exercises `from chirp.cli._templates import STYLE_CSS, V2_APP_PY` so the shim must remain.
- No external grep evidence (can only check this repo) that the 3 unused names have any consumer.
- `CLAUDE.md` explicitly says: *"Don't use feature flags or backwards-compatibility shims when you can just change the code."* → no deprecation period for the 3 dead names; just delete.

The shim keeps working for `STYLE_CSS` and `V2_APP_PY` (what the test actually imports); it just stops re-exporting 3 names nothing uses.

### Task 0.3 — Scaffold count ✅

**Decision: Fold the OOB demo into the existing `v2` dashboard in Sprint 5. Do not add a new `--oob` scaffold mode.**

Rationale:
- `V2_DASHBOARD_CHIRPUI_HTML:415-421` already has a `<tbody data-grid-body>` with rows and a filter/sort button — a natural OOB target (POST → return `OOB(Fragment(..., "grid_body"), Fragment(..., "grid_stats"))`).
- New scaffold modes cost docs, help text, CLI flag, test coverage, and support surface. Folding is ~20 lines added to an existing template.
- `register_oob_region` can still be shown inside the v2 `app.py`.

### Task 0.4 — Page handler signature convention ✅

**Decision: Canonical scaffold form is `def get(request: Request) -> Page` and `async def post(request: Request) -> Page | Redirect` (both fully typed). When the handler needs no request, drop the param: `def get() -> Page`.**

Evidence:
- `examples/chirpui/contacts_shell/pages/contacts/page.py:6,17` — fully typed both sides (`def get(request: Request) -> Page`, `async def post(request: Request) -> Page`).
- `examples/chirpui/kanban_shell/pages/login/page.py:7,23` — untyped request, typed return (`def get(request) -> Page`, `async def post(request) -> Page | Redirect`).
- Other variants in examples: `def get() -> Page`, `def get() -> Redirect`, `def get(projects: tuple[...]) -> Page` (context-injected params).

Scaffolds are pedagogical; typed is the stronger signal. Match contacts_shell. This also means:
- **Sprint 2.2 revision**: login POST returns `Page | Redirect` (not just `Page`), since happy-path redirects to `next_url`.
- **Shell scaffold** (Sprint 2.4): apply typed form even though current `SHELL_PAGE_PY` uses `async def handler()` with no context.

---

## Sprint 1: Version Bumps & Dead-Code Cleanup

**Goal**: Close the gap between what scaffolds emit and what the repo ships, without changing any framework behavior.

### Task 1.1 — Bump `PYPROJECT_TOML` version floors

**File**: `src/chirp/cli/templates/scaffold.py:15,19`
Change `"bengal-chirp>=0.2.0"` → `"bengal-chirp>=0.4.0"`; `"chirp-ui>=0.2.0"` → `"chirp-ui>=0.3.0"`.

**Acceptance**: `grep -n "bengal-chirp\|chirp-ui" src/chirp/cli/templates/scaffold.py` shows only `>=0.4.0` / `>=0.3.0`.

### Task 1.2 — Remove dead imports from `V2_APP_PY`

**File**: `src/chirp/cli/templates/v2.py:9-10`
Delete `EventStream,` and `Fragment,` from the `from chirp import (...)` block — the non-UI variant never defines the `/time` stream.

**Acceptance**: `grep -c "EventStream\|Fragment" src/chirp/cli/templates/v2.py` drops; scaffolded project still imports cleanly.

### Task 1.3 — Remove bare `import chirp_ui` from `V2_APP_CHIRPUI_PY`

**File**: `src/chirp/cli/templates/v2.py:103`
Delete line `import chirp_ui`. Registration via `use_chirp_ui(app)` (already imported from `chirp`) is sufficient.

**Acceptance**: `grep -n "^import chirp_ui" src/chirp/cli/templates/v2.py` returns nothing.

### Task 1.4 — Retire `full.py` per Sprint 0.2 decision

Either delete `src/chirp/cli/templates/full.py` and move `TEST_APP_PY`/`STYLE_CSS` into `sse.py` (the only consumer), or rename to `_legacy.py` and emit a warning when imported. Update `templates/__init__.py` re-exports either way.

**Acceptance**: `grep -rn "from chirp.cli.templates.full\|from chirp.cli.templates import APP_PY\|BASE_HTML\|INDEX_HTML" src/` returns only what remains after the decision.

### Task 1.5 — Use canonical top-level imports in SSE scaffold

**File**: `src/chirp/cli/templates/sse.py:4-6`
Rewrite `from chirp.streaming import EventStream, Fragment` and `from chirp.templating import Template` to a single `from chirp import App, EventStream, Fragment, Request, Template`. Matches all `examples/standalone/*/app.py`.

**Acceptance**: Scaffold diff shows single `from chirp import ...` at top; project still runs.

> **Sprint 1 verification discovery**: The submodule imports (`chirp.streaming`, `chirp.templating`) did **not** resolve at runtime — `chirp.streaming` doesn't exist as a module, and `Template` isn't re-exported at `chirp.templating` (lives at `chirp.templating.returns`). Scaffolds generated pre-Sprint-1 produced apps that failed at import time. This was a latent bug, not just a style issue.

### Task 1.6 — Apply the same fix to `minimal.py`

**File**: `src/chirp/cli/templates/minimal.py:4-5`
Same pattern: `from chirp.templating import Template` → `from chirp import App, Request, Template`.

Found during Sprint 1 verification — `chirp new --minimal` produced an app that failed at import with `ImportError: cannot import name 'Template' from 'chirp.templating'`. Not in the original plan because the audit agent missed it; documented here as a natural extension of 1.5.

**Acceptance**: `uv run --project . chirp new --minimal /tmp/x && cd /tmp/x && python -c "import app; app.app.freeze()"` returns `freeze OK`.

---

## Sprint 2: V2 Handler Conversion (scope narrowed — see note below)

**Goal**: Every v2 page uses the method-named handler (`get`/`post`) that current examples use, AND the `/login` POST handler lives in the login `page.py` instead of the top-level `app.py`.

> **Scope change (2026-04-20)**: The draft folded `Template(...)` → `Page(..., "page_content", page_block_name="page_root", ...)` into Sprint 2. That swap requires the page templates to define `page_root`/`page_root_inner`/`page_content` blocks — Sprint 4's job. Sprint 1 verification already confirmed the v2 scaffold today produces apps with 6 `app.check()` ERRORs because those blocks don't exist. Swapping in `Page(...)` now would leave the scaffold in a worse state until Sprint 4 lands. **Deferred to Sprint 4**, where it naturally groups with the template migration. Sprint 2 keeps `Template(...)` returns. Verified that the page router (`src/chirp/pages/discovery.py:39,544`) recognizes `get`/`post`/`put`/etc. by function name and treats the legacy `handler` as a GET-only fallback — so `async def handler()` currently maps to GET anyway; the rename is a pure pedagogical/readability change for the scaffold.

### Task 2.1 — `V2_INDEX_PAGE_PY` → `def get(request)` + `Page`

**File**: `src/chirp/cli/templates/v2.py:277-283`
Replace:
```python
async def handler():
    return Template("page.html")
```
with:
```python
from chirp import Page, Request

def get(request: Request) -> Page:
    return Page("page.html", "page_content", page_block_name="page_root")
```

**Acceptance**: `grep -n "async def handler\|Template(" src/chirp/cli/templates/v2.py` drops to 0 in index PY.

### Task 2.2 — `V2_LOGIN_PAGE_PY` → `def get` / `async def post`

**File**: `src/chirp/cli/templates/v2.py:304-311`
Split `handler(request)` into `get(request)` (renders form) and `async def post(request)` (validates + redirects or returns error). POST body lives here, not in `app.py:/login` — matches `examples/chirpui/kanban_shell/pages/login/page.py`.

**Acceptance**: Two top-level functions named `get` and `post` in the login page string; `/login` route handler in v2 app.py becomes unnecessary (or is deleted in favor of the page handler).

### Task 2.3 — `V2_DASHBOARD_PAGE_PY` → `def get` + `Page`

**File**: `src/chirp/cli/templates/v2.py:360-370`
Replace `async def handler():` with `def get(request: Request) -> Page` and return `Page("dashboard/page.html", "page_content", page_block_name="page_root", user=get_user(), cols=_GRID_COLUMNS)`. `@login_required` remains.

**Acceptance**: `grep -n "def handler\|Template(" src/chirp/cli/templates/v2.py` returns 0 after this task + 2.1.

### Task 2.4 — Shell scaffold handler conversion

**File**: `src/chirp/cli/templates/shell.py` (SHELL_PAGE_PY, SHELL_ITEMS_PAGE_PY)
Apply the same conversion. Shell already uses `_context.py`, which stays.

**Acceptance**: `grep -rn "async def handler" src/chirp/cli/templates/` returns 0.

---

## Sprint 3: V2 Login → `Page(..., error=...)` mirroring `kanban_shell`

**Goal**: The scaffolded login flow teaches the filesystem-routed login pattern used in the only login example in the repo — `examples/chirpui/kanban_shell/pages/login/page.py`.

> **Changed from draft**: Sprint 0.1 flipped this away from `ValidationError`. A scaffolded `login/page.py` using `ValidationError` would be scaffold-only (no example to grep to), violating invariant 3. `kanban_shell` is the canonical shape.

### Task 3.1 — POST handler returns `Page` on bad creds (from `V2_LOGIN_PAGE_PY`)

**File**: `src/chirp/cli/templates/v2.py` — login POST (moved into `V2_LOGIN_PAGE_PY` per Task 2.2)
On bad creds, return:
```python
return Page(
    "login/page.html",
    "page_content",
    page_block_name="page_root",
    error="Invalid username or password",
)
```
On success, `login(user)` + `Redirect(next_url if is_safe_url(next_url) else "/")`. Drop the `Redirect("/login?error=1")` + query-param dance from `v2.py:69` entirely; the `/login` route in `V2_APP_PY` is deleted (Task 2.2 already moves it into the page).

**Acceptance**: `grep -n "error=1" src/chirp/cli/templates/v2.py` returns 0.

### Task 3.2 — Login template reads `error` kwarg directly

**File**: `V2_LOGIN_HTML`, `V2_LOGIN_CHIRPUI_HTML`
Current template already reads `{% if error %}...{% end %}` — the fix is on the handler side (Task 3.1). Verify the template still renders the error cleanly; remove the query-param error-prefill logic from `V2_LOGIN_PAGE_PY` (`request.query.get("error", "")`).

**Acceptance**: `grep -n 'request.query.get("error"' src/chirp/cli/templates/v2.py` returns 0. Bad login → re-rendered form shows "Invalid username or password".

### Task 3.3 — Update `V2_TEST_APP_PY` login failure test

**File**: `src/chirp/cli/templates/v2.py:531-547`
Change the failure assertion from `assert r.status == 302; assert "error=1" in r.header("location", "")` to `assert r.status == 200; assert "Invalid" in r.text`.

**Acceptance**: Generated test matches generated handler; `uv run pytest` passes in scaffolded project.

**Note on `ValidationError`**: It remains the right pattern for form POSTs that submit mid-app-flow (creating a contact, editing a task). The v2 scaffold doesn't have any such form — only the login form. A future scaffold addition (e.g. a "notes" CRUD mode) would be the right place to teach `ValidationError`.

---

## Sprint 4: V2 Templates → Composition

**Goal**: Every v2 page template uses `page_root → page_root_inner → page_content` blocks and does **not** `{% extends %}` a `_layout.html`. The Chirp filesystem router composes layout + page via `render_with_blocks`.

### Task 4.1 — Rewrite `V2_INDEX_HTML` / `V2_INDEX_CHIRPUI_HTML`

**File**: `src/chirp/cli/templates/v2.py:285-302`
Remove `{% extends "_layout.html" %}`. Wrap content in:
```
{% block page_root %}
<div id="page-root">
{% block page_root_inner %}
{% block page_content %}
  ...
{% end %}
{% end %}
</div>
{% end %}
```
Mirror the pattern in `examples/chirpui/kanban_shell/pages/login/page.html`.

**Acceptance**: `grep -c "{% extends" src/chirp/cli/templates/v2.py` drops by 2 per page file rewritten.

### Task 4.2 — Rewrite `V2_LOGIN_HTML` / `V2_LOGIN_CHIRPUI_HTML`

Same pattern. Form body lives inside `page_content`.

**Acceptance**: Template has 3 blocks (`page_root`, `page_root_inner`, `page_content`) and no `extends`.

### Task 4.3 — Rewrite `V2_DASHBOARD_HTML` / `V2_DASHBOARD_CHIRPUI_HTML`

Same pattern. The `time_block` block stays at top level for SSE targeting.

**Acceptance**: Dashboard composes into layout; SSE block still works (verify via TestClient + SSE assertion).

### Task 4.4 — Update `V2_LAYOUT_HTML` / `V2_LAYOUT_CHIRPUI_HTML` if needed

**File**: `src/chirp/cli/templates/v2.py:211-275`
Layouts already have `{% block content %}{% endblock %}` — rename to `{% block page_root %}{% end %}` only if required to match filesystem routing conventions. Check `src/chirp/templating/` for what `render_with_blocks` expects.

**Acceptance**: Freshly scaffolded v2 app renders `/` without `BlockNotFoundError`; `app.check()` is clean.

---

## Sprint 5: Showcase Additions (Optional)

**Goal**: At least one scaffold demonstrates `Suspense` or `OOB`. Skippable if Sprint 0.3 rules it out.

### Task 5.1 — Add OOB demo to v2 dashboard (or new `--oob` mode)

Per Sprint 0.3 decision:
- **Folded into v2**: add a small "draft status" button on the dashboard that POSTs and returns `OOB(Fragment("dashboard/page.html", "draft_status_main"), Fragment("dashboard/page.html", "draft_status_badge"))`.
- **Separate `--oob` mode**: minimal project with one POST route showing a two-target swap.

**Acceptance**: Scaffolded project imports `OOB` from `chirp` and the OOB route round-trips via TestClient.

### Task 5.2 — Optional: Suspense demo

If time allows, the dashboard's "grid data" + "stats" could demo `Suspense` with `defer_blocks`:
```python
return Suspense("dashboard/page.html", defer_blocks=("stats_block", "grid_block"), stats=load_stats(), rows=load_rows())
```
Requires `load_stats()` / `load_rows()` to be awaitables with small artificial `asyncio.sleep` for demo.

**Acceptance**: Scaffolded dashboard renders shell with skeleton placeholders, then streams deferred blocks.

---

## Sprint 6: Snapshot & Contract Tests

**Goal**: Lock in the modernization so a future edit can't silently regress a scaffold.

### Task 6.1 — Freeze-and-check tests per scaffold

**File**: `tests/cli/test_scaffold_contracts.py` (new)
For each mode (`minimal`, `sse`, `shell`, `v2`, `v2+ui`), in a tmp dir:
1. Run `create_project(tmp, name, mode)`.
2. Exec the generated `app.py`; call `app.freeze()`.
3. Assert `app.check()` returns no ERROR issues.

**Acceptance**: `uv run pytest tests/cli/test_scaffold_contracts.py -v` passes for every mode.

### Task 6.2 — Grep-invariant tests

**File**: `tests/cli/test_scaffold_patterns.py` (new)
Assert:
- No scaffold template string contains `"async def handler"` or `"def handler("`.
- Every v2 page template string contains `"{% block page_root %}"` and no `"{% extends \"_layout.html\" %}"`.
- `scaffold.py` version floors are `>=<root_version_major_minor>`.

**Acceptance**: Tests run against the source strings themselves — fast, deterministic.

### Task 6.3 — TestClient smoke of generated project (golden path)

**File**: `tests/cli/test_scaffold_runtime.py` (new)
For `v2`: scaffold → import → `TestClient` → GET `/`, POST `/login` happy + sad path, GET `/dashboard` unauth → 302, GET `/dashboard` auth → 200 with user name.

**Acceptance**: All generated v2 assertions pass end-to-end without hand-editing the project.

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `render_with_blocks` behaves differently than examples suggest — scaffolded `v2` pages fail to render after Sprint 4 | Medium | High | Sprint 4 Task 4.4 explicitly verifies against `src/chirp/templating/` before edits; Sprint 6.3 smoke test catches any miss |
| External users depend on removed `full.py` exports | Low | Medium | Sprint 0.2 investigates; worst case rename to `_legacy.py` with a deprecation warning instead of delete |
| `ValidationError` flow breaks CSRF test expectations | Medium | Medium | Sprint 3.3 updates generated tests alongside handler; keep CSRF happy-path unchanged |
| `Page(..., page_block_name="page_root")` expects layout structure that v2 layout doesn't have | Medium | High | Sprint 4.4 reconciles layout blocks with page blocks; Sprint 6.1 catches via `app.check()` |
| Suspense showcase (Sprint 5) leaks scope, delays shipping | Medium | Low | Sprint 5 is explicitly optional; Sprints 1-4 + 6 deliver value on their own |

---

## Success Metrics

| Metric | Current | After Sprint 2 | After Sprint 6 |
|--------|---------|----------------|---------------|
| Scaffolds using current intent types (`Page`, `OOB`; `Suspense`/`ValidationError` deferred) | 0/5 | 3/5 (v2, v2+ui, shell using `Page`) | 3/5 + OOB demo folded into v2 dashboard (Sprint 5) |
| Scaffolds with stale version floors | 1 (`scaffold.py`, affects all) | 0 | 0 |
| V2 page files using `async def handler()` | 3 | 0 | 0 |
| V2 page templates using `{% extends "_layout.html" %}` | 6 | 6 | 0 |
| Dead imports in generated `app.py` | 3 (`EventStream`, `Fragment`, `import chirp_ui`) | 0 | 0 |
| Scaffold contract/grep/runtime tests | 0 | 0 | **46** (5 contract + 39 grep + 2 runtime) |

---

## Relationship to Existing Work

- **`docs/rfcs/001-component-filter-contract.md`** — parallel — unaffected; scaffolds don't emit component filters.
- **`examples/chirpui/contacts_shell/`**, **`examples/chirpui/kanban_shell/`** — prerequisite evidence — scaffold rewrites follow their shape.
- **Agent-DX epic (commit 7680bd1)** — supersedes, in part — that epic closed "vibe coding" gaps in the framework; this epic closes the remaining gap in *what `chirp new` teaches*.
- **Fragment target registry (commit 4f63c6b)** — parallel — `register_oob_region` is what Sprint 5 Task 5.1 (OOB demo) would exercise.

---

## Changelog

| Date | Change | Reason |
|------|--------|--------|
| 2026-04-20 | Initial draft | Scaffold audit on `lbliii/verify-scaffolds` branch confirmed 10 concrete gaps |
| 2026-04-20 | Sprint 0 complete | Four design decisions recorded. Sprint 3 pivoted from `ValidationError` to `Page(..., error=...)` — mirrors `kanban_shell/pages/login/page.py`, which is the only login example in the repo. `full.py` will be deleted after moving `TEST_APP_PY`/`STYLE_CSS` to `sse.py`. OOB demo folds into v2 dashboard (no new scaffold mode). Canonical handler signature: `def get(request: Request) -> Page` / `async def post(request: Request) -> Page \| Redirect`. |
| 2026-04-20 | Sprint 1 complete | Version floors bumped (0.4.0/0.3.0); dead `EventStream`/`Fragment` imports removed from `V2_APP_PY`; bare `import chirp_ui` removed; `full.py` deleted, `TEST_APP_PY`/`STYLE_CSS` relocated to `sse.py`, `_templates.py` shim and `__init__.py` updated; SSE imports canonicalized to top-level `chirp`. **Bonus find**: `minimal.py` also had the broken `from chirp.templating import Template` submodule import (doesn't resolve — Template lives at `chirp.templating.returns`). Fixed to `from chirp import App, Request, Template`. All 11 `tests/test_cli_new.py` pass. `minimal`/`sse`/`shell` scaffolds freeze cleanly. `default`/`with-chirpui` still report 6 `app.check()` ERRORs — all are the page-shell-contract `page_root/page_root_inner/page_content` block mismatch; Sprint 4 territory, not regressions. |
| 2026-04-20 | Sprint 2 complete | Handler rename across all templates: `V2_INDEX_PAGE_PY`, `V2_DASHBOARD_PAGE_PY`, `SHELL_PAGE_PY`, `SHELL_ITEMS_PAGE_PY` all use `def get() -> Template`. `V2_LOGIN_PAGE_PY` split into `def get(request) -> Template` and `async def post(request) -> Redirect` — login POST moved out of `V2_APP_PY`/`V2_APP_CHIRPUI_PY` to `pages/login/page.py`; app.py now only owns the `/logout` (and CHIRPUI `/time` SSE) routes. Template→Page swap deferred to Sprint 4 (requires composition blocks first). Verified by confirming `pages.login.page` exposes `get`/`post` and `pages.page`/`pages.dashboard.page` expose `get`. All 11 `tests/test_cli_new.py` pass. Freeze behavior unchanged vs Sprint 1: `minimal`/`sse`/`shell` clean; `default` still blocked by the 6 pre-existing PageShellContract ERRORs (Sprint 4). |
| 2026-04-20 | Sprint 3 complete | `V2_LOGIN_PAGE_PY.post()` returns `Page("login/page.html", "content", error="Invalid username or password")` on bad creds instead of `Redirect("/login?error=1")`. `get()` no longer reads `?error=` from query. `V2_TEST_APP_PY` `test_login_failure` flipped from `status==302 + "error=1" in location` to `status==200 + "Invalid" in text`. **Minor deviation from plan**: used `"content"` block (not `"page_content" + page_block_name="page_root"`) because the scaffold templates still define `{% block content %}`; Sprint 4 will upgrade the Page signature alongside the template block migration. End-to-end verified: BAD login → 200 w/ "Invalid"; GOOD login → 302 → /dashboard. All 7 generated pytest tests pass. All 11 scaffold tests pass. UserWarning about missing `page_block_name` is expected — flagged for Sprint 4 uplift. |
| 2026-04-21 | Sprint 6 complete | Added `tests/cli/` package with three test files + a shared `conftest.py` (scaffold helper + subprocess runner that isolates `App()` global state across parametrized runs). **Task 6.1** (`test_scaffold_contracts.py`): 5 tests — one per mode (`minimal`, `sse`, `shell`, `v2`, `v2_plain`). Each scaffolds → subprocess imports `app` → calls `app.freeze()` with `CHIRP_SKIP_CONTRACT_CHECKS=1` → inspects `check_hypermedia_surface(app).errors`. All 5 pass. **Task 6.2** (`test_scaffold_patterns.py`): 39 tests — textual assertions against template strings. Locks in Sprint 1–5 invariants: no `async def handler` / `def handler(`; every v2 page template has `{% block page_root %}` + `{% block page_content %}` and lacks `{% extends "_layout.html" %}`; every v2 page module passes `page_block_name="page_root"`; login never uses `?error=1`; `V2_APP_PY` has no dead `EventStream`/`Fragment` imports; `V2_APP_CHIRPUI_PY` has no bare `import chirp_ui`; `scaffold.py` version floors track root `pyproject.toml` (`bengal-chirp>=X.Y.x`, `chirp-ui>={ui.extra.version}`); OOB showcase (safe_region + blocks) is wired. Pattern tests read the live pyproject, so future version bumps auto-enforce. **Task 6.3** (`test_scaffold_runtime.py`): 2 tests — scaffold `v2` and `v2_plain` → subprocess TestClient flow covering `/`, `/login` happy+sad, `/dashboard` unauth+auth, and `/dashboard/refresh` OOB (200 w/ counter+hx-swap-oob for chirpui; 404 for plain v2). **Verification**: 46 new tests + 11 existing `test_cli_new.py` = 57 tests, all pass in 5.2s. ruff clean. Epic done. |
| 2026-04-21 | Sprint 5 complete | Folded OOB demo into `V2_DASHBOARD_CHIRPUI_HTML` (new "OOB two-target swap" card) + `V2_APP_CHIRPUI_PY` (`/dashboard/refresh` POST returning `OOB(Fragment("refresh_counter"), Fragment("refresh_stamp", target="refresh-stamp", swap="innerHTML"))`). Main fragment replaces `#refresh-counter` innerHTML; stamp fragment OOB-swaps the stamp div's innerHTML, preserving its `chirpui-text-muted` class. Counter wrapper uses `safe_region("refresh-counter")` from `chirpui/fragment_island.html` to satisfy the MutationTargetContract (hx-disinherit). In-memory state via module-level `itertools.count(1)`; `@login_required` protects the route. Added `test_dashboard_refresh_oob` to `V2_TEST_APP_PY`, gated on route presence (returns early on 404) so it also passes on the non-chirpui variant. Task 5.2 (Suspense demo) skipped per plan — explicitly optional. **Verification**: plain v2 + v2+chirpui freeze with 0 errors; 8/8 generated pytest tests pass in both variants; 11/11 `tests/test_cli_new.py` tests pass; ruff clean. |
| 2026-04-20 | Sprint 4 complete | All 6 v2 page templates (`V2_INDEX_HTML` + `_CHIRPUI`, `V2_LOGIN_HTML` + `_CHIRPUI`, `V2_DASHBOARD_HTML` + `_CHIRPUI`) migrated from `{% extends "_layout.html" %}{% block content %}...{% endblock %}` to composition: `{% block page_root %}<div id="page-root">{% block page_root_inner %}{% block page_content %}...{% end %}{% end %}</div>{% end %}`. Dashboard `time_block` preserved as sibling top-level block for SSE fragment targeting. Handlers upgraded: `V2_INDEX_PAGE_PY` uses `Page("page.html", "page_content", page_block_name="page_root")`; `V2_LOGIN_PAGE_PY` get/post both use `Page(..., "page_content", page_block_name="page_root", ...)`; `V2_DASHBOARD_PAGE_PY` same. `Template` import dropped from login/dashboard/index page modules (Page covers both full + fragment modes). Layouts unchanged — `{% block content %}` is the composition slot consumed by `render_with_layouts` (`src/chirp/pages/renderer.py:100`); pages flow in as rendered HTML. **Result: chirpui v2 freeze goes from 6 errors → 0 errors.** All 7 generated pytest tests pass. All 11 scaffold tests pass. Dashboard smoke test confirms `id="page-root"` renders, SSE `sse-connect="/time"` present. |
