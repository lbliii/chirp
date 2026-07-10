# Backlog-truth automation

> Make "done" a fact a machine derives, not a checkbox a human ticks.

**Issue templates:** `.github/ISSUE_TEMPLATE/` — use **Saga**, **Epic**, **Task**,
**RFC / research**, or **Bug** when opening work. Templates link here; do not
duplicate scope in repo planning files.

In a fast, agent-driven repo, PRs merge faster than anyone reconciles the
issues and epics that spawned them — so the tracker rots. (A June 2026 sweep
found **13 epics fully shipped yet still open**, with stale checkboxes.) The
root cause: *intent* lives in prose (issue bodies, `plan/*.md`, the roadmap) and
*state* lives in code, with nothing bridging the two.

This machinery closes that gap with three small, stdlib-only, no-network pieces
plus a structured git convention. None of it is a required check by default —
adopt enforcement (branch protection) once markers are in common use.

## 1. `@pytest.mark.issue(N)` — acceptance as a test

Tag the test(s) that prove a GitHub issue's acceptance criteria:

```python
import pytest

@pytest.mark.issue(143)
async def test_introspect_postgres_roundtrip():
    ...

@pytest.mark.issue(166, 174)   # one test can prove criteria for several issues
class TestShapecheckDrift:
    ...
```

The marker is registered in `pyproject.toml` (`--strict-markers` is on). Query
coverage offline:

```bash
python scripts/issue_coverage.py            # issues that have acceptance tests
python scripts/issue_coverage.py --issue 143
python scripts/issue_coverage.py --json
```

"Is #143 done?" becomes "do its `@pytest.mark.issue(143)` tests pass?" — which
the normal test job already answers.

## 2. The closure gate — `Closes #N` must come with a test

`scripts/check_closure_acceptance.py` (wired as the **Issue closure gate**
workflow) fails a PR whose body says `Closes #N` (or `Fixes`/`Resolves`) when no
`@pytest.mark.issue(N)` test exists. It's the forcing function: you can't *claim*
closure without *proving* it.

Issues with no testable criterion (positioning, pure docs) opt out explicitly,
and auditably, in the PR body:

```
Acceptance: n/a (docs-only)
```

## 3. Structured git trailers — lean on git itself

Reference issues in PR bodies / commits with the conventions the tooling reads:

- `Closes #143` / `Fixes #143` — GitHub auto-closes the issue on merge; the gate
  requires a matching acceptance test.
- `Advances-Epic: #174` — credits an epic without closing it (epics close when
  their children do).
- The `issue-<N>-...` branch name is also read as a strong "this PR is for #N"
  signal.

## 4. The reconciliation sweep — heal residual drift

`scripts/reconcile_backlog.py` (wired as the **Backlog reconciliation**
workflow, weekly + manual) re-derives backlog truth from merged PRs × the
sub-issue/epic graph × acceptance coverage, and applies derived labels so a
human sweeps labels in minutes instead of re-triaging from zero:

| Label | Meaning |
|---|---|
| `merged-pending-close` | A merged PR closes this non-epic issue — verify & close. |
| `stale-epic-review` | An epic whose work merged — re-check children / close. |
| `acceptance-tracked` | The issue has an executable acceptance test. |

It is **read-only by default** (prints a Markdown report); the scheduled run
passes `--apply` to attach labels. Run a dry-run locally any time:

```bash
python scripts/reconcile_backlog.py            # report only
python scripts/reconcile_backlog.py --apply     # also (idempotently) labels issues
```

## Rollout

1. Land this PR — nothing becomes blocking; the gate/sweep are inert until used.
2. Open new work through `.github/ISSUE_TEMPLATE/` (Saga, Epic, Task, RFC /
   research, Bug). Prefer **GitHub sub-issues** over markdown `- [ ]` checklists
   in sagas and epics, so parent progress is maintained by GitHub, not by hand.
3. Tag acceptance tests with `@pytest.mark.issue` as issues are worked.
4. Once adoption is broad, mark **Issue closure gate** as a required status check
   in branch protection to make the forcing function binding.

## Issue templates

| Template | When to use | Default labels | Body shape (Furatena + Chirp) |
| --- | --- | --- | --- |
| **Saga** | Cross-cutting strategic thread | `saga`, `roadmap` | North star, release gates, workstreams, success signal |
| **Epic** | Major initiative under a saga | `epic` | Parent saga, outcome, dependencies, **exit criteria** |
| **Task** | Actionable leaf work | (add `P*` + domain labels) | Parent epic, **depends on**, outcome, scope, proof, acceptance |
| **RFC / research** | Design before implementation | `rfc`, `research` | What, why, research questions, promotion criteria |
| **Bug** | Verified defect or regression | `bug`, `correctness` | Repro, expected/actual, regression proof |

Hierarchy: **Saga → Epic → Task** as GitHub sub-issues. RFC issues may spawn an
`implementation-epic` and task children when promoted.

Suggested manual labels after opening (namespaced style used in Furatena/Elbysodic;
Chirp also keeps legacy flat `P1`, `hypermedia`, etc.):

| Family | Examples |
| --- | --- |
| Priority | `P0`–`P3` (or `priority:p0` when migrating) |
| Domain | `hypermedia`, `contracts`, `streaming`, `ai`, `dx`, … |
| Workflow | `ready`, `research`, `decision-needed`, `upstream-blocked` |
| Automation | `merged-pending-close`, `acceptance-tracked`, `stale-epic-review` |

All templates link to this document for closure conventions. Blank issues are
disabled — pick a template or ask a maintainer.
