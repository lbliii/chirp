# AGENTS.md

## Steward: Test Matrix Steward

This domain protects the repository's executable safety net: unit tests, integration tests,
concurrency tests, negotiation tests, CLI tests, docs tests, examples tests, and helpers.

## Must Not Become

- A pile of snapshots that bless broken hypermedia.
- A substitute for contract tests when public rendering behavior changes.
- A slow suite with no fast path for contributors.

## Documentation Ownership

Update root `AGENTS.md`, README health notes, roadmap gates, and docs when test commands or coverage
expectations change.

## Local Checks

Use the narrowest relevant subset first, then escalate:

- `uv run pytest tests/ -q --tb=short --timeout=60 -m "not slow"`
- `uv run pytest examples/ -q --tb=short --timeout=60 -m "not slow"` for example-facing changes
- `uv run pytest tests/test_concurrency -q` for shared state or free-threading changes

## Public Contracts And Safety Boundaries

- Hypermedia surface changes need end-to-end `TestClient` coverage in `tests/contracts/`.
- Tests should exercise the interesting branch: htmx vs non-htmx, missing block, malformed form,
  async vs sync context, and production vs debug where relevant.
- Keep coverage at or above the configured 80 percent floor.
