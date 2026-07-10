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

This machinery closes that gap with stdlib-only derivation and validation,
`gh`-backed GitHub survey/application commands, and a structured git
convention. None of it is a required check by default — adopt enforcement
(branch protection) once markers are in common use.

## Agent survey, cut, and groom workflow

The supported operations are:

| Trigger | Effect |
| --- | --- |
| `survey backlog` / `survey issues` | Read-only evidence-backed state report |
| `what should I work on` / `pick next issue` | Rank immediately workable leaves and explain why |
| `groom backlog` / `groom issues` | Update issue state, decisions, labels, hierarchy, and verified closures |
| `cut work` / `cut issue` / `make #N workable` | Create bounded leaves and attach actual sub-issues |
| `reconcile backlog` / `close shipped issues` | Verify merged work and close only fully resolved issues |

For each operation:

1. Record the current `main` SHA and query scope.
2. Read the actual GitHub parent/sub-issue graph, issue bodies/comments, merged
   PRs, acceptance markers, and relevant current source/docs.
3. Classify each item as complete, partial, not started, rejected, superseded,
   upstream-blocked, or dependency-blocked.
4. Research unstable upstream facts from primary sources.
5. Close verified-complete or resolved decisions. Split residual scope instead
   of reusing a completed issue.
6. Create missing leaves and attach them through GitHub's sub-issue
   relationship. Same-repo blockers use native dependency relationships.
7. Ensure each unblocked parent reaches a ready leaf. Parents never carry
   `ready`.
8. Re-query the graph and emit a grooming receipt.

### Workability contract

Hierarchy is **Saga → Epic → Task** through actual GitHub sub-issues. Issue-body
parent fields and links are descriptive only.

- Sagas and epics contain outcomes, cross-child exit gates, boundaries, and
  decisions. They do not contain `- [ ] #N` child-status lists.
- A task with unresolved dependencies or approval is not `ready`.
- A fully blocked parent names the blocker and a concrete revisit trigger.
- An accepted RFC records its decision, opens a separate implementation epic
  and bounded task children when needed, then closes as a decision issue.
- A completed issue is never retitled or repurposed for follow-up work.

Record decisions in the issue using:

```text
Decision — YYYY-MM-DD
Status: approved / rejected / deferred / superseded
Evidence:
Decision:
Rejected alternatives:
Implementation owner: #N / none
Revisit trigger:
```

### Backlog plan tool

Agents turn an approved decomposition into ephemeral JSON rather than another
checked-in backlog. The tool is dry-run-first:

```bash
uv run --no-project python scripts/backlog.py audit
uv run --no-project python scripts/backlog.py doctor --strict
uv run --no-project python scripts/backlog.py next --limit 5
uv run --no-project python scripts/backlog.py explain 678
uv run --no-project python scripts/backlog.py validate /tmp/backlog-plan.json
uv run --no-project python scripts/backlog.py apply /tmp/backlog-plan.json
uv run --no-project python scripts/backlog.py apply /tmp/backlog-plan.json --apply
```

Minimal create plan:

```json
{
  "version": 1,
  "repository": "lbliii/chirp",
  "baseline_sha": "<surveyed HEAD>",
  "preconditions": {
    "343": {"updated_at": "<surveyed updatedAt>"}
  },
  "actions": [
    {
      "id": "signal-compiler",
      "kind": "create",
      "issue_kind": "task",
      "title": "Task: compile the private signal graph",
      "labels": ["P2", "reactive", "contracts", "ready"],
      "parent": 343,
      "blocked_by": [],
      "idempotency_key": "signal-compiler-v1",
      "spec": {
        "outcome": "One immutable graph is authoritative.",
        "immediate_action": "Add the failing topology fixture.",
        "scope": "Compile existing producer, dependency, and sink facts.",
        "boundaries": "No public API or severity change.",
        "proof": "Determinism, mounted apps, and concurrent-read tests.",
        "acceptance": "Existing findings remain stable.",
        "collateral": "RFC implementation status; no changelog."
      }
    }
  ]
}
```

Every existing issue touched directly or as a parent/blocker needs a
`preconditions` entry with its surveyed `updated_at`; content edits may also
include `body_sha256`. Close actions additionally require evidence and
`--allow-close`.

Create actions use stable remote markers, actual parent/blocker relationships,
stale-state preconditions, and leaf-only workflow labels. `ready` is applied
after hierarchy and blockers. Close actions run last and require
`--allow-close`. Interrupted applications write a local journal and resume only
with `--resume`.

### Choosing the next workable issue

The read-only recommender turns the same live graph into an agent context
packet:

```bash
uv run --no-project python scripts/backlog.py next --limit 5
uv run --no-project python scripts/backlog.py next --area templating --kind bug
uv run --no-project python scripts/backlog.py next --json
uv run --no-project python scripts/backlog.py explain 678
uv run --no-project python scripts/backlog.py explain 678 --json
```

An issue is eligible only when it is open, non-GF maintainer work, an explicit
`ready` leaf, free of blocked state and open formal blockers, reachable through
a healthy native parent chain, not waiting on a decision, and not claimed by an
open PR. An explicit closing reference or `issue-<N>-...` branch claims work;
bare issue mentions do not. The body must identify an immediate action.

Eligible issues are ranked deterministically by effective priority (including
ancestor roadmap priority), direct downstream unlock count, age, then issue
number. `--area` matches domain labels, namespaced area/component labels, and
repository paths in the issue or its ancestors. `--kind` accepts `task`, `rfc`,
or `bug`.

The output includes the immediate action, required proof, parent chain, areas,
open-PR state, and warnings. New forms use canonical execution headings;
legacy issues can derive equivalent context from `Decision to record`,
`Outcome`, `Scope`, `Required proof plan`, `Exit`, or an unstructured first
action paragraph, and the output says when it did so. Missing proof remains a
visible grooming warning.

`next` and `explain` never label, assign, comment on, or claim an issue. A
future claim operation should be a separate explicit mutation with expiry and
collision handling.

Every mutating pass ends with a receipt:

```text
Backlog Grooming Receipt
Baseline: <main SHA>, <UTC timestamp>, <scope>

Closed:
- #N — disposition — evidence

Created and attached:
- #child -> #parent — labels — immediate action

Decisions:
- #N — decision — evidence — revisit trigger

Ready leaves:
- #N — first action

Blocked:
- #N — blocker — revisit trigger

Verification:
- graph re-query
- reconciliation/workability report
- acceptance coverage
- GF inventory unchanged
```

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

Issues with no testable criterion opt out per closing issue, explicitly and
auditably, in the PR body:

```
Acceptance #143: n/a (docs-only; no runtime behavior)
```

A PR closing several issues needs acceptance proof or its own qualified
exemption for each issue. A bare global `Acceptance: n/a` exempts nothing.

## 3. Structured git trailers — lean on git itself

Reference issues in PR bodies / commits with the conventions the tooling reads:

- `Closes #143` / `Fixes #143` — GitHub auto-closes the issue on merge; the gate
  requires a matching acceptance test.
- `Advances-Epic: #174` associates partial work with a parent without closing
  it; epics close when their children do.
- The `issue-<N>-...` branch name associates a PR with an issue but never
  implies closure. Only explicit closing keywords are closing intent.

## 4. The reconciliation sweep — heal residual drift

`scripts/reconcile_backlog.py` (wired as the **Backlog reconciliation**
workflow, weekly + manual) re-derives backlog truth from explicit merged-PR
closure intent × the native sub-issue graph × acceptance coverage, and applies
convergent derived labels so a
human sweeps labels in minutes instead of re-triaging from zero:

| Label | Meaning |
|---|---|
| `merged-pending-close` | A merged PR closes this non-epic issue — verify & close. |
| `stale-epic-review` | An epic whose work merged — re-check children / close. |
| `acceptance-tracked` | The issue has an executable acceptance test. |
| `closure-candidate` | All native child issues completed; verify parent gates. |
| `needs-grooming` | Work state or hierarchy violates the workability contract. |
| `needs-decomposition` | An unblocked parent has no native children. |

It is **read-only by default** (prints a Markdown report). Scheduled runs stay
read-only while the graph-aware rules soak; a maintainer can opt into label
updates from a manual workflow run. Run a dry-run locally any time:

```bash
python scripts/reconcile_backlog.py --report-workability --with-dependencies
python scripts/reconcile_backlog.py --with-dependencies --snapshot /tmp/backlog.json
python scripts/reconcile_backlog.py --report-workability --with-dependencies --apply
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

Hierarchy: **Saga → Epic → Task** as actual GitHub sub-issues. Parent fields in
issue forms do not attach issues. RFCs close when their decision is recorded;
approved implementation moves to a separate `implementation-epic` and tasks.

Suggested manual labels after opening (namespaced style used in Furatena/Elbysodic;
Chirp also keeps legacy flat `P1`, `hypermedia`, etc.):

| Family | Examples |
| --- | --- |
| Priority | `P0`–`P3` (or `priority:p0` when migrating) |
| Domain | `hypermedia`, `contracts`, `streaming`, `ai`, `dx`, … |
| Workflow | `ready`, `research`, `decision`, `blocked`, `upstream-blocked` |
| Automation | `merged-pending-close`, `acceptance-tracked`, `closure-candidate`, `needs-grooming`, `needs-decomposition` |

`ready` is reserved for actionable RFC/task/bug leaves whose dependencies and
approvals are satisfied. Never apply it to a saga, epic, or implementation
epic.

All templates link to this document for closure conventions. Blank issues are
disabled — pick a template or ask a maintainer.
