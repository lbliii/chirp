# RFC: Contract diff — hypermedia surface change reports

**Status:** Draft (prototype landed)  
**Issue:** #344  
**Parent:** Horizon #335

## Problem

PR reviews and agent loops see line diffs, not hypermedia surface changes. Chirp already
machine-checks routes, fragments, OOB targets, SSE wiring, and forms at startup — that
surface should be diffable.

## v0 shape (implemented)

- `chirp check APP --json` emits a stable JSON payload via `result_to_dict()`
- `chirp check APP --baseline PATH` diffs against a prior JSON run
- Fingerprints: `(severity, category, route, template, message)`
- CI policy: fail on **new errors**; optional fail on new warnings with `--warnings-as-errors`

## Next steps

1. `chirp diff --base origin/main APP` CLI that runs check twice without a committed baseline
2. GitHub Action posting PR comments from `--json` diff output
3. MCP tool `chirp_surface_diff` for agent consumption
4. Merge-blocking policy steward sign-off (ERROR-only vs WARNING)

## Non-goals (v0)

- Full template source diff
- Auto-fix suggestions
- Diffing INFO / design-system manifest noise (excluded by default)
