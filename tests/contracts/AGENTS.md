# AGENTS.md

## Steward: Contract Test Steward

This domain protects end-to-end tests for `app.check()` and the public hypermedia contract surface.

## Must Not Become

- Unit tests for private helper functions with a contract label.
- A noisy suite that locks in message wording without checking user actionability.
- A place to hide severity changes without reviewer visibility.

## Documentation Ownership

Update `docs/hypermedia-footguns.md`, contract plans, examples, and root guidance when new contract
categories or severity behavior land.

## Local Checks

Start with:

- `uv run pytest tests/contracts -q`
- `uv run pytest tests/test_cli_check.py tests/test_terminal_checks.py -q`
- `uv run pytest tests/contracts/test_checker_integration.py -q` for checker lifecycle changes

## Public Contracts And Safety Boundaries

- Every contract test should create a realistic app path through `TestClient` or `app.check()`.
- Expected issues should prove category, severity, location, and next-action clarity.
- Preserve tests for both default severity and `override_contract_severity` when changing policy.
