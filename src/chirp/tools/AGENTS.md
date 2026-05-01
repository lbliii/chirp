# AGENTS.md

## Steward: Tools And MCP Steward

This domain protects tool registration, schemas, event buses, MCP handler integration, and the
public extension surface for LLM-callable functions.

## Must Not Become

- An untyped arbitrary function executor.
- A hidden side channel around Chirp's route, app, and lifecycle contracts.
- A mutable global registry shared across apps.

## Documentation Ownership

Update README feature notes, `docs/public-api.md`, and examples when tool registration or schema
behavior changes.

## Local Checks

Start with:

- `uv run pytest tests/test_tools tests/test_plugin.py -q`
- `uv run pytest tests/test_app/test_service_injection.py -q` when app integration changes
- `uv run ruff check src/chirp/tools`

## Public Contracts And Safety Boundaries

- Tool definitions and event shapes are provisional public API.
- Registries must freeze with the app lifecycle and avoid cross-app leakage.
- Schema generation should be deterministic and explicit about unsupported Python types.
