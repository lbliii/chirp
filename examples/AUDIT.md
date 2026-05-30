# Chirp Examples Audit

Analysis of all examples for similar issues and outdated patterns (Feb 2025).
Based on fixes applied to the hackernews example.

## 2026 Reactive and Forum Pattern Audit

Newer examples add production-shaped patterns that were not present in the
original Feb 2025 audit:

| Example | Canonical Pattern | Notes |
|---------|-------------------|-------|
| **reactive_tasks** | `ReactiveBus` + `DependencyIndex` + `reactive_stream()` | Shows `ConnectionInfo`, presence-aware streams, origin filtering, changed-path updates, and reactive contract metadata. Use this as the current reactive baseline. |
| **chirpui/forum_shell** | Product-shaped shell contract fixture | Demonstrates mounted pages, ChirpUI shell navigation, repeated-field `FormContract` binding, JSON data islands, OOB unread count, and app-shell-safe targets. It is a regression fixture for downstream product risks, not a full production forum or product seed. |
| **returns_gallery** | Return-type reference | Covers `Page`, `Fragment`, `OOB`, `Suspense`, `EventStream`, `ValidationError`, `FormAction`, `Action`, `Stream`, and `Redirect`. Keep it aligned with the return-type architecture. |

Current SSE guidance:

- Untargeted yielded `Fragment` values emit unnamed SSE frames and are received
  by htmx's default `sse-swap="message"` listener.
- Use explicit `Fragment(..., target="name")` only for named channels.
- Use `{% fragment %}` for swap-only payload blocks; keep Suspense shell slots
  as `{% block %}` so skeletons render on first paint.
- Put `sse-swap` on a child sink, not on the `sse-connect` element, and use
  `hx-disinherit="hx-target hx-swap"` to isolate long-lived streams from broad
  layout targets.

Current downstream-product fixture guidance:

- Keep `forum_shell` small. It should prove contracts that downstream products
  depend on, not grow product workflows.
- Its tests should keep asserting full-page shell rendering, boosted outlet
  rendering, repeated-field form binding, JSON data-island shape, OOB shell
  updates, and `check_hypermedia_surface()` coverage.
- When a downstream app exposes a reusable gap, add the smallest fixture or
  contract test that reproduces the framework issue. Leave product semantics,
  schema, moderation, permissions, and workflow state in the downstream app.

Current contract proof guidance:

- Reactive examples should register `reactive_index`, `reactive_emitted_paths`,
  and `reactive_connection_scopes` so `app.check()` can catch block, path, and
  audience drift.
- If an example emits `ChangeEvent(audience=...)`, it should also declare
  `reactive_audience_scopes` and pass `ConnectionInfo(user_id=...)` from the
  stream route.
- Example tests should assert clean contract output for the framework behavior
  the README claims, not only that the page renders.

## Examples Expansion (Feb 2025)

Documentation and new examples added:

| Change | Details |
|--------|---------|
| **kanban**, **theming** | Documented in README (were missing from examples list) |
| **production** | SecurityHeadersMiddleware + SessionMiddleware + CSRFMiddleware, contact form, security header tests |
| **custom_middleware** | Function-based timing middleware, class-based rate limiter, `Response.with_header()` |
| **accessibility** | Semantic HTML, skip link, ARIA, focus styles, `ValidationError` form |
| **api** | Pure JSON CRUD, `dict`/`list` returns, path params, `request.json()`, CORSMiddleware |

## HTML Spec Alignment (Feb 2025)

Security and accessibility updates:

| Change | Example(s) |
|--------|------------|
| `SessionMiddleware` + `CSRFMiddleware` + `csrf_field()` | rag_demo |
| `chirp[ai,data,sessions,markdown]` install | rag_demo |
| `url` filter, `safe(reason=...)`, SecurityHeadersMiddleware | Library (see docs) |

## Upgrade Round (Feb 2025) — {% imports %}, sse_scope, dark theme

All examples upgraded for consistency and S-tier DX:

| Example | Upgrades |
|---------|----------|
| **hackernews** | `{% imports %}`, `sse_scope`, `nav_link`, view-transition |
| **dashboard_live** | `{% imports %}`, `sse_scope`, view-transition meta |
| **dashboard** | `{% imports %}`, `sse_scope`, meta charset/viewport |
| **chat** | Dark theme, `{% globals %}` for chat_message |
| **sse** | Dark theme, meta charset/viewport |
| **kanban** | `{% imports %}` (replaced `{% globals %}` for from imports) |
| **contacts** | Dark theme, meta charset/viewport |
| **todo** | Dark theme, meta charset/viewport |
| **auth** | Dark theme, meta charset/viewport |
| **wizard** | Dark theme, meta charset/viewport |
| **signup** | Dark theme, meta charset/viewport |

## Issues Found

### 1. Pounce imports (outdated)

**Pattern**: `from pounce.config import ServerConfig`  
**Preferred**: `from pounce import ServerConfig` (aligned with bengal)

| Example       | Status |
|---------------|--------|
| dashboard     | ✅ Fixed |
| rag_demo      | ✅ Fixed |
| hackernews    | ✅ Fixed |

### 2. SSEEvent import (submodule vs public API)

**Pattern**: `from chirp.realtime.events import SSEEvent`  
**Preferred**: `from chirp import SSEEvent`

| Example | Status |
|---------|--------|
| ollama  | ✅ Fixed |
| sse     | ✅ Uses `from chirp import SSEEvent` |
| hackernews | ✅ Uses `from chirp import SSEEvent` |

### 3. SSE + OOB flicker (load flicker on connect)

**Cause**: Yielding an initial `Fragment` on SSE connect that matches existing content triggers htmx to swap the whole page with itself → visible flicker.

**Fix**: Yield `SSEEvent(event="ping", data="connected")` first; avoid sending an initial OOB fragment that duplicates page content.

| Example       | Pattern | Status |
|---------------|---------|--------|
| hackernews    | Had initial Fragment on connect | ✅ Fixed (ping first) |
| sse           | Yields `"connected"` string first, then Fragments | ✅ OK (no OOB on connect) |
| dashboard_live| Waits 2–5s before first Fragment | ✅ OK (no immediate OOB) |
| ollama        | User-driven; no initial fragment on connect | ✅ OK |

### 4. View transitions + OOB (whole-page erase)

**Cause**: `view-transition-name` on a parent of OOB targets (e.g. `#main`) causes OOB swaps to trigger the full-page transition animation → "whole page erased" effect.

**Fix**: Scope `view-transition-name` to elements that change only on full navigation (e.g. `.story-detail`), not on parents of OOB targets.

| Example       | Uses view-transition? | Status |
|---------------|-----------------------|--------|
| hackernews    | Yes — was on `#main` | ✅ Fixed (moved to `.story-detail`) |
| dashboard_live| No | ✅ N/A |
| sse           | No | ✅ N/A |
| contacts      | No | ✅ N/A |

### 5. Run instructions (pip vs uv)

**Pattern**: Many examples used `pip install chirp[...]` + `cd examples/X && python app.py`.  
**Preferred** (from repo root): `PYTHONPATH=src python examples/<bucket>/X/app.py`

| Example       | Current | Notes |
|---------------|---------|-------|
| hackernews    | `uv run python app.py` | ✅ Updated |
| examples/README | `PYTHONPATH=src python examples/<bucket>/X/app.py` | Updated to repo-root commands |
| Most others   | `pip install` + `python app.py` | Works when chirp installed |

## Patterns to Apply

1. **Pounce**: `from pounce import ServerConfig` and `from pounce.server import Server`
2. **Chirp**: `from chirp import SSEEvent` (not `chirp.realtime.events`)
3. **SSE + OOB**: Ping on connect; avoid initial OOB fragment that matches page content
4. **View transitions**: (a) Avoid `view-transition-name` on parents of OOB targets; scope to navigation-only elements. (b) Avoid `transition:true` on the swap target container — put it only on nav links to prevent OOB swaps from triggering full-area flicker

## Examples README Guidance

The `examples/README.md` View Transitions section previously recommended manually adding `view-transition-name: page-content` to `#main`. This is now handled automatically by `chirpui-transitions.css` (included when using `app_shell_layout.html`). The stylesheet also suppresses root transitions and disables VT on `.chirpui-fragment-island` elements. Apps that use OOB swaps inside `#main` should still scope `view-transition-name` to nav-only content (not parents of OOB targets) — see the standalone hackernews example for this pattern.
