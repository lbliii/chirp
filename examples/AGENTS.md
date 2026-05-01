# AGENTS.md

## Steward: Examples-As-Docs Steward

This domain protects standalone and ChirpUI examples as executable documentation for real app
patterns.

## Must Not Become

- A gallery of outdated snippets that pass only because nobody runs them.
- A showcase for unsafe htmx inheritance, broad OOB targets, or duplicated JSON APIs.
- A place to demonstrate framework abstractions before they are stable enough for users.

## Documentation Ownership

Update example READMEs, root README feature links, `examples/AUDIT.md`, and relevant docs when an
example becomes canonical for a pattern.

## Local Checks

Start with:

- `uv run pytest examples/ -q --tb=short --timeout=60 -m "not slow"`
- `uv run pytest tests/test_chirpui_boundary.py -q` for ChirpUI-facing examples
- `uv run pytest tests/contracts -q` when examples exercise new contract rules

## Public Contracts And Safety Boundaries

- Examples should prefer public imports from `chirp`.
- Streaming examples must distinguish `Stream`, `Suspense`, and `EventStream` by use case.
- If a pattern would be unsafe in a real app, do not teach it here.
