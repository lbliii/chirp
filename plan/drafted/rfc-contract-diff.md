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
- `chirp diff APP --base REF` runs check at *REF* (via git worktree) and diffs against HEAD
- Fingerprints: `(severity, category, route, template, message)`
- CI policy: fail on **new errors**; optional fail on new warnings with `--warnings-as-errors`
- PR workflow (`.github/workflows/contract-diff.yml`) posts an advisory comment via `scripts/contract_diff_pr_comment.py`

## Next steps

1. ~~GitHub Action posting PR comments from `--json` diff output~~ (advisory comment shipped)
2. ~~MCP tool `chirp_surface_diff` for agent consumption~~ (`register_surface_diff_tool()`)
3. Merge-blocking policy steward sign-off (ERROR-only vs WARNING)

## Non-goals (v0)

- Full template source diff
- Auto-fix suggestions
- Diffing INFO / design-system manifest noise (excluded by default)
