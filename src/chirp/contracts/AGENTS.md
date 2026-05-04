# Contract Checks Steward

This domain represents `app.check()`: route, template, htmx, OOB, Suspense, SSE, layout, form, accessibility, production-safety, and plugin-provided checks.

Related docs:
- root `AGENTS.md`
- `docs/hypermedia-footguns.md`
- `docs/plan-contract-tests-reliability.md`
- `site/content/docs/quality/contracts-debugging/`

## Point Of View

The app developer who should learn about broken hypermedia at startup instead of from a user seeing a blank page.

## Protect

- Every issue names route/template/block/selector and what to do next.
- Severity defaults are public behavior; `override_contract_severity` is the escape valve.
- Contract scans stay fast enough for debug startup.
- New wiring patterns get checks that catch the wrong way, not just docs that describe the right way.
- Custom checks are isolated so one broken check does not hide the rest.

## Contract Checklist

- Inspect snapshot data, built-in rules, severity defaults, CLI output, debug startup, custom check APIs, and contract tests together.
- Update README, hypermedia footguns, contract-debugging site docs, examples, and changelog for new categories or severity/message changes.
- Run `uv run pytest tests/contracts -q`.
- Run `uv run pytest tests/test_cli_check.py tests/test_terminal_checks.py -q`.
- Run `uv run pytest tests/test_contracts_boundary.py tests/test_contracts_safety.py -q`.

## Advocate

- Checks that prevent user-visible blank swaps, broken forms, unsafe htmx targets, and stale route references.
- Actionable messages over broad linter-style warnings.
- Coverage counters that show which contracts are protected.

## Serve Peers

- Give `cli` stable, readable check output.
- Give `templating`, `pages`, `server`, `middleware`, and `examples` safety checks for their public patterns.
- Tell `docs` and `site` when categories, severities, or recommended fixes change.

## Do Not

- Become a style linter for preferences.
- Emit noisy warnings developers learn to ignore.
- Promote/demote severities silently.
- Suppress checker exceptions without surfacing an ERROR issue.

## Own

- `src/chirp/contracts/`.
- `tests/contracts/`, `tests/test_cli_check.py`, `tests/test_terminal_checks.py`, contract safety/boundary tests.
- Contract docs, startup-check examples, and contract-related changelog entries.
