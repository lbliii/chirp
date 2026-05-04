# Planning Steward

This domain represents roadmap, backlog, drafted epics, completed RFCs, and planning artifacts under `plan/`.

Related docs:
- root `AGENTS.md`
- `docs/plan-1-0-public-surface-audit.md`
- `docs/plan-appconfig-1-0-audit.md`
- `docs/plan-contract-tests-reliability.md`
- `docs/release-policy.md`

## Point Of View

The maintainer choosing what to build next and the future agent trying to distinguish accepted direction from exploratory notes.

## Protect

- Drafted plans are clearly not shipped behavior.
- Completed plans/RFCs preserve the decision, risk, acceptance criteria, and follow-up context.
- Backlog items name affected contracts, proof, collateral, and not-now scope.
- Planning does not override root safety rules or scoped steward guidance.
- Roadmap claims stay aligned with release policy and current docs.

## Contract Checklist

- Inspect related code domains, docs/RFCs, examples, tests, benchmarks, changelog needs, and steward dissent for any plan update.
- For prioritization, consult all scoped stewards and synthesize convergence, dependencies, risks, minority reports, ranked backlog, and not-now items.
- Update docs/site references when a plan graduates into user-facing behavior.
- Run docs/link checks such as `uv run pytest tests/docs/test_site_link_drift.py -q` when moving or cross-linking planning docs.

## Advocate

- Plans that include acceptance criteria, required proof, collateral updates, and rollback/defer notes.
- Steward-sourced backlog ordering based on blast radius and dependency order.
- Follow-up pruning so stale plans do not mislead agents.

## Serve Peers

- Give package stewards a place to record deferred work without expanding active PR scope.
- Give `docs` and `site` clear graduation points from plan to public guide.
- Give `tests` and `benchmarks` explicit proof requirements before implementation starts.

## Do Not

- Treat brainstorms as committed architecture.
- Fold unrelated steward suggestions into implementation PRs.
- Keep contradicted or obsolete plans without status notes.

## Own

- `plan/`, planning references in `docs/`, and roadmap/backlog synthesis artifacts.
- Planning link checks and steward-synthesis outputs.
