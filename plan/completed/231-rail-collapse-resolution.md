# Resolution: #231 Lucky Cat rail — revert drag-resizer to cookie-collapse

**Status**: Complete
**Created**: 2026-06-15
**Completed**: 2026-06-15
**Source**: Backlog reconciliation of the Lucky Cat epic (#220) after PR #240 merged.

---

## Decision

Revert the Lucky Cat progressive rail from a **continuous drag-resizer** back to
**cookie-collapse only**, honoring the locked owner decision recorded in #231.

## Why (the divergence)

#231's *locked* owner decision #1 reads:

> **Collapse = elbysodic pattern** (collapse the inner rail to the icon rail;
> cookie-persisted; **server-side first-paint** so there's no flash). **NOT a
> continuous drag-resizer.**

The issue further reserved resizable rails for the peer package explicitly:

> a first-class chirp-ui resizable-rail macro would be a peer-package change and
> is **explicitly out of scope here**.

PR #240 nonetheless shipped a bespoke continuous drag-resizer ("BUILD 2"): a
`.luckycat-sidebar-resize` pointer-drag handle, a `luckycat_rail_width` cookie,
`shell.rail_width()` server clamp, `--luckycat-rail-width` CSS var, and ~200
lines of `static/lucky-cat-shell.js`. That is unreviewed scope-creep into
territory the owner explicitly reserved for the chirp-ui peer package, and it
contradicts an emphatic locked decision.

## Resolution applied

Reverted to cookie-collapse only (the original acceptance criteria are met — the
collapse was always present alongside the resizer):

- `static/lucky-cat-shell.js` — replaced the drag-resizer IIFE with a small
  collapse-toggle controller (cookie read/write + `[data-luckycat-rail-toggle]`
  click, delegated off `document` so it survives OOB rail swaps). The hero-chart
  crosshair IIFE is untouched.
- `shell.py` — removed `RAIL_WIDTH_COOKIE` / `RAIL_WIDTH_MIN_PX` /
  `RAIL_WIDTH_MAX_PX` / `rail_width()`; kept `rail_is_collapsed()` (server-side
  no-FOUC reader).
- `app.py` — dropped the `rail_width` template global; kept `rail_is_collapsed`.
- `pages/_layout.html` — removed `sidebar_resize_handle` + the
  `--luckycat-rail-width` pre-size; kept the cookie-gated pre-collapse `<style>`.
- `static/lucky-cat.css` — removed the resize-handle / dragging styles + the
  resizable comment; kept `--luckycat-rail-width` as a fixed inner-rail token and
  the `.luckycat-rail--collapsed` rules.
- `test_app.py` — `TestRailCollapse` rewritten to assert the collapse toggle +
  the server-side no-FOUC pre-collapse `<style>`; drag-resize/width tests removed.

## Acceptance (what closes #231)

The original locked acceptance criteria, all still satisfied:

- Outer icon rail persists across routes; inner contextual rail changes by route.
- Boosted navigation swaps the inner rail via the single `sidebar_oob` region.
- Collapse toggles to the icon rail and **persists across reload with no flash**
  (server cookie + pre-render). Proof: `@pytest.mark.issue(231)` on
  `TestRailCollapse::test_collapsed_cookie_pre_renders_collapsed_state`.
- `app.check()` ERROR-free; active-state highlighting intact.

## Follow-up (forward note for the peer package)

A first-class **resizable rail** belongs in the **chirp-ui** package as a macro,
not hand-rolled per example. The reverted bespoke implementation (pointer-drag +
keyboard + ARIA splitter + server-clamped width cookie) is preserved in git
history (PR #240) as a reference for that future peer-package feature. Until then
examples should use the collapse-only pattern.
