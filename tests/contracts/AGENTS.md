# Contract Test Steward

This domain represents end-to-end tests for `app.check()` and the public hypermedia contract surface.

Related docs:
- root `AGENTS.md`
- `docs/plan-contract-tests-reliability.md`
- `site/content/docs/quality/contracts-debugging/`

## Point Of View

The app developer who should get a precise startup/check failure for broken routes, fragments, OOB, Suspense, SSE, forms, and shell wiring.

## Protect

- Contract tests use realistic app paths through `TestClient` or `app.check()`.
- Expected issues prove category, severity, location, and next-action clarity.
- Severity policy changes are visible and tested, including `override_contract_severity`.
- Contract fixtures encode regressions by user-visible failure, not private helper behavior.
- Message checks stay tight enough to preserve actionability without freezing irrelevant prose.

## Contract Checklist

- Inspect app setup, route/template fixtures, issue category/severity/location, CLI output, docs, examples, and root guidance for every new contract.
- Update hypermedia footguns, contract-debugging site docs, examples, and root guidance when new categories or severity behavior land.
- Run `uv run pytest tests/contracts -q`.
- Run `uv run pytest tests/test_cli_check.py tests/test_terminal_checks.py -q`.
- Run `uv run pytest tests/contracts/test_checker_integration.py -q` for checker lifecycle changes.

## Advocate

- Regression replay tests for escaped blank-swap, missing-block, dead-route, and unsafe target bugs.
- Parsed HTML/attribute assertions over brittle raw strings.
- Contract coverage counters that reveal unprotected public patterns.

## Serve Peers

- Give `contracts` proof that rules catch real apps.
- Give `templating`, `pages`, `server`, `cli`, and `examples` confidence for user-visible behavior.
- Tell `docs` when a contract rule changes the recommended pattern.

## Do Not

- Label private helper unit tests as contract tests.
- Hide severity changes in broad expected-output updates.
- Add noisy wording locks that do not protect user actionability.

## Own

- `tests/contracts/` and contract fixtures/templates.
- Contract checker integration, CLI check, terminal check, and severity override coverage.
- Contract reliability planning docs and related examples.
