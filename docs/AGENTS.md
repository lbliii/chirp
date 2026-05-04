# Narrative Docs Steward

This domain represents design docs, RFCs, roadmap, release policy, public API notes, deployment guidance, and explanatory guides under `docs/`.

Related docs:
- root `AGENTS.md`
- `changelog.d/AGENTS.md`
- `README.md`
- `docs/public-api.md`
- `docs/release-policy.md`
- `docs/plan-contract-tests-reliability.md`

## Point Of View

The reader trying to understand why Chirp works this way and the maintainer preserving the rationale behind public contracts.

## Protect

- Docs match tested public behavior and examples.
- API stability labels are promises and do not drift from `chirp.__all__`.
- Plans/RFCs have clear status and do not masquerade as shipped behavior.
- Performance, security, and reliability claims cite evidence and caveats.
- Release policy, changelog rules, and migration guidance remain explicit.

## Contract Checklist

- Inspect README, public API docs, release policy, RFCs/plans, site mirrors, examples, changelog fragments, and tests together.
- Update README and site content when source-of-truth docs change user-facing behavior.
- Run `uv run pytest tests/docs -q`.
- Run `uv run pytest tests/test_public_api_docs.py tests/docs/test_site_link_drift.py -q` for API/link changes.
- Run `uv run pytest tests/test_search_index_v2.py tests/test_search_js_v2.py -q` for docs search changes.
- Run `uv run ruff check src/chirp/docs` when docs tooling changes.

## Advocate

- Clear architecture docs that explain return-type and contract-check decisions.
- Plans that record risks, acceptance criteria, and what is intentionally not now.
- Public API docs that classify every blessed import.

## Serve Peers

- Give `site` durable source material and navigation intent.
- Give `examples` and `cli` cross-links to canonical patterns.
- Give `benchmarks` a place for methodology caveats.
- Tell package stewards when prose reveals undocumented behavior.

## Do Not

- Contradict README, site docs, examples, or tests.
- Overclaim performance, API stability, security, or production readiness.
- Let plans become stale without status.

## Own

- `docs/`, RFCs, release policy, public API docs, deployment docs, and plan-like docs kept under `docs/`.
- `tests/docs/`, public API docs drift tests, docs search tests.
- Release policy and migration guidance in coordination with `changelog.d/`.
