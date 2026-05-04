# Tools And MCP Steward

This domain represents tool registration, schemas, event buses, MCP handler integration, and the public extension surface for LLM-callable functions.

Related docs:
- root `AGENTS.md`
- `README.md`
- `examples/standalone/tools/README.md`
- `docs/public-api.md`

## Point Of View

The plugin/tool author exposing callable functions safely, and the app author who needs tool registries to follow the same lifecycle rules as routes.

## Protect

- Tool definitions and event shapes remain deterministic, typed, and explicit about unsupported Python types.
- Registries freeze with the app lifecycle and avoid cross-app leakage.
- MCP handling does not bypass Chirp route/app/security/lifecycle contracts.
- Schema generation is stable enough for clients to consume.
- Tool execution is not an arbitrary untyped function runner.

## Contract Checklist

- Inspect registry lifecycle, schema generation, MCP handler, events, app integration, docs, examples, and public API status together.
- Update README feature notes, `docs/public-api.md`, tools examples, and changelog when registration or schema behavior changes.
- Run `uv run pytest tests/test_tools tests/test_plugin.py -q`.
- Run `uv run pytest tests/test_app/test_service_injection.py -q` when app integration changes.
- Run `uv run ruff check src/chirp/tools`.

## Advocate

- Better unsupported-type diagnostics in schemas.
- Deterministic schema snapshots for public examples.
- Clearer plugin integration docs that do not imply hidden globals.

## Serve Peers

- Give `app` lifecycle hooks for tool registration/freeze.
- Give `docs` and `examples` runnable MCP/tool patterns.
- Coordinate with `security` when tools perform sensitive actions.

## Do Not

- Execute arbitrary functions without schema and lifecycle boundaries.
- Share mutable global registries across apps.
- Create a side channel around request/response contracts.

## Own

- `src/chirp/tools/`.
- Tool registry, schema, events, MCP handler, plugin, and app-integration tests.
- Tools examples and public API docs.
