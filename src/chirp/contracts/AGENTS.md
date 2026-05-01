# AGENTS.md

## Steward: Contract Checks Steward

This domain protects `app.check()`: route, template, htmx, OOB, Suspense, SSE, layout, form,
accessibility, production-safety, and plugin-provided checks.

## Must Not Become

- A style linter for preferences that do not prevent user-visible failure.
- A noisy warning source that developers learn to ignore.
- A hidden breaking change by silently promoting or demoting severities.

## Documentation Ownership

Update README, `docs/hypermedia-footguns.md`, contract reliability plans, and relevant examples
when adding checks or changing message shape.

## Local Checks

Start with:

- `uv run pytest tests/contracts -q`
- `uv run pytest tests/test_cli_check.py tests/test_terminal_checks.py -q`
- `uv run pytest tests/test_contracts_boundary.py tests/test_contracts_safety.py -q`

## Public Contracts And Safety Boundaries

- Every issue should name the route/template/block/selector and what to do next.
- Severity defaults are public behavior; use `override_contract_severity` as the escape valve.
- New hypermedia wiring needs a check that catches the wrong way, plus an end-to-end contract test.
- Contract scans must stay fast enough for debug startup.
