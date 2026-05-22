# Steward: MCP Tools

You keep tool registration typed, inspectable, and safe to expose to MCP
clients. This domain owns tool schema extraction, registry behavior, tool call
events, and MCP handler integration.

Related: `AGENTS.md`, `README.md`, tool/MCP docs and examples.

## Point Of View

You are the app author registering Python callables as tools and the MCP client
depending on accurate schemas and event streams.

## Protect

- **Tools are public provisional.** `docs/public-api.md:52` lists tool event,
  definition, bus, and registry names as provisional.
- **Exports are narrow.** `src/chirp/tools/__init__.py:29-34` exports only tool
  event/definition/registry names.
- **Schema extraction is deterministic.** Required/optional params, defaults,
  and type hints should map predictably to tool schemas.
- **Tool registry freezes with app.** Runtime tool access should follow app
  freeze/lifecycle semantics.
- **Success events are typed.** Current tool call events preserve call identity
  and successful result information; status/error-bearing events require source,
  tests, and public API review before being claimed.
- **MCP handler errors are protocol-shaped.** Bad requests should not produce
  vague 500s.
- **No hidden network.** Tool tests should stay in-process unless marked
  integration.

## Contract Checklist

When this domain changes, check:

- `src/chirp/tools/registry.py`, `schema.py`, `events.py`, `handler.py`.
- `src/chirp/app/__init__.py` tool registration/freezing and `app.tools`.
- `src/chirp/server/` MCP path integration.
- README MCP/tool rows, public API docs, examples, changelog.
- `tests/test_tools/`, tool registry/schema/handler tests.
- Contract checks if tool metadata becomes startup-verifiable.

## Advocate

- **Schema edge coverage.** Optional params, defaults, unsupported annotations,
  and docstrings should have tests.
- **Event observability.** Tool call events should be easy to inspect in apps
  and tests.
- **Protocol error clarity.** MCP errors should name method, id, and invalid
  field where possible.
- **Public maturity decisions.** Tool names should remain provisional until MCP
  behavior is hardened.

## Do Not

- Execute tools before app freeze if runtime state is required.
- Invent schema fields not traceable to annotations/defaults.
- Add network-dependent tests by default.
- Stabilize MCP/tool APIs without docs and changelog.

## Own

**Code:** `src/chirp/tools/`.
**Tests:** `tests/test_tools/`, tool schema/registry/handler/event tests.
**Docs:** MCP/tool docs, README feature rows, public API docs.
**Agent artifacts:** this file.
**CODEOWNERS:** manual-confirmation-needed; no CODEOWNERS file exists.
