# RFC: Contract diff — hypermedia surface change reports

**Status:** Accepted (v0 shipped)  
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
- CI policy: **fail on new ERRORs**; warnings remain advisory unless `--warnings-as-errors` / `--deploy`
- PR workflow (`.github/workflows/contract-diff.yml`) posts a comment via `scripts/contract_diff_pr_comment.py` and exits non-zero on new errors
- MCP tool `chirp_surface_diff` via `register_surface_diff_tool()` for agent consumption

## Research answers

| Question | Decision |
|----------|----------|
| Diff algorithm | Snapshot before/after: run `chirp check --json` at base ref (git worktree) and HEAD, diff issue fingerprints |
| GitHub Action / PR comment | `scripts/contract_diff_pr_comment.py` upserts a marker comment on every PR sync |
| Agent MCP tool | `chirp_surface_diff(base_ref=...)` returns JSON payload with `baseline`, `current`, `diff`, `summary_lines` |
| Stable JSON schema | `result_to_dict()` / check payload; diff keys on `(severity, category, route, template, message)` |

## Merge-blocking policy

- **ERROR:** new contract errors in the diff block merge (CI `--fail-on-new-errors`)
- **WARNING:** advisory in default posture; promoted to blocking with `--deploy` or `--warnings-as-errors`
- **INFO:** excluded unless `--include-info`

## Agent loop pattern

1. Agent edits templates/routes
2. Agent calls `chirp_surface_diff` (MCP) or `chirp diff APP --base origin/main --json`
3. Diff lists added/removed issues with route/template context — not line counts
4. Agent fixes wiring until `added_errors` is empty and `chirp check` is green

Local equivalent: `chirp diff examples.chirpui.forum_shell.app:app --base origin/main`

## Non-goals (v0)

- Full template source diff
- Auto-fix suggestions
- Diffing INFO / design-system manifest noise (excluded by default)

## Future (post-v0)

- Surface diff in `chirp diff --format github` for generic CI
- Actionable fix hints tied to each added issue category
- Optional merge-blocking on new warnings via repo policy file
