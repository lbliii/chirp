# Chirp Examples Audit

Analysis of all examples for similar issues and outdated patterns (Feb 2025).
Based on fixes applied to the hackernews example.

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
| `chirp[ai,data,sessions]` install | rag_demo |
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

**Pattern**: Many examples use `pip install chirp[...]` + `cd examples/X && python app.py`.  
**Preferred** (from b-stack root): `uv run python chirp/examples/X/app.py`

| Example       | Current | Notes |
|---------------|---------|-------|
| hackernews    | `uv run python app.py` | ✅ Updated |
| examples/README | `cd examples/X && python app.py` | Consider adding uv option |
| Most others   | `pip install` + `python app.py` | Works when chirp installed |

## Patterns to Apply

1. **Pounce**: `from pounce import ServerConfig` and `from pounce.server import Server`
2. **Chirp**: `from chirp import SSEEvent` (not `chirp.realtime.events`)
3. **SSE + OOB**: Ping on connect; avoid initial OOB fragment that matches page content
4. **View transitions**: (a) Avoid `view-transition-name` on parents of OOB targets; scope to navigation-only elements. (b) Avoid `transition:true` on the swap target container — put it only on nav links to prevent OOB swaps from triggering full-area flicker

## Examples README Guidance

The `examples/README.md` View Transitions section (lines 280–291) recommends:

```css
#main { view-transition-name: page-content; }
```

**Update**: Add a warning that if `#main` (or similar) is a parent of OOB targets, this can cause the whole-page-erase bug. Prefer scoping to elements that change only on full navigation.
