# AGENTS.md

## Steward: Routing Steward

This domain protects route definitions, path parameters, router matching, named routes, mount
composition, and URL generation dependencies.

## Must Not Become

- A second filesystem router. Filesystem page discovery lives in `pages`.
- A request dispatcher. Handler invocation and negotiation belong in `server`.
- A permissive matcher that hides ambiguous or unreachable routes.

## Documentation Ownership

Update README, `docs/routing/mounting.md`, relevant RFCs, and site routing docs when route syntax,
params, named routes, or mount behavior changes.

## Local Checks

Start with:

- `uv run pytest tests/test_route.py tests/test_router.py tests/test_params.py -q`
- `uv run pytest tests/test_url_for.py tests/test_mount_app.py tests/contracts/test_routes.py -q`
- `uv run pytest tests/test_route_directory_contract_e2e.py -q` when route discovery interaction changes

## Public Contracts And Safety Boundaries

- 404 and 405 behavior must stay actionable and include method/path/allowed-method details.
- Path param conversion is a public behavior once route authors depend on it.
- Routing changes can invalidate contracts, examples, and generated scaffolds; check downstream.
