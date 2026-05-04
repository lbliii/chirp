# Routing Steward

This domain represents route definitions, path parameters, router matching, named routes, mount composition dependencies, and URL generation inputs.

Related docs:
- root `AGENTS.md`
- `docs/routing/mounting.md`
- `docs/rfcs/003-named-routes.md`
- `docs/rfcs/004-url-for.md`
- `site/content/docs/build-apps/pages-navigation/`

## Point Of View

The app author who expects a path and method to resolve predictably, and the downstream systems that use route names, params, and mounted paths as contracts.

## Protect

- 404 and 405 behavior stays actionable and names method/path/allowed methods.
- Path param conversion is public once route authors depend on it.
- Ambiguous, duplicate, or unreachable routes are not hidden by permissive matching.
- Route names and URL generation stay deterministic across mounts.
- Filesystem discovery remains in `pages`; request dispatch remains in `server`.

## Contract Checklist

- Inspect route syntax, param conversion, method dispatch, name registration, URL generation, mount prefix behavior, and contract checks together.
- Update README, routing docs, site pages, RFCs, examples, scaffolds, and changelog when public route behavior changes.
- Run `uv run pytest tests/test_route.py tests/test_router.py tests/test_params.py -q`.
- Run `uv run pytest tests/test_url_for.py tests/test_mount_app.py tests/contracts/test_routes.py -q`.
- Run `uv run pytest tests/test_route_directory_contract_e2e.py -q` when page discovery interaction changes.

## Advocate

- Better diagnostics for duplicate names, path type errors, and route shadowing.
- Contract coverage for every public routing feature.
- URL generation ergonomics that do not invent a second routing model.

## Serve Peers

- Give `pages` a clean route registration target.
- Give `server` unambiguous handler matches.
- Give `contracts` route tables with enough metadata for htmx/form/link validation.
- Give `cli` stable route output.

## Do Not

- Build a filesystem router here.
- Dispatch requests or negotiate return values here.
- Accept ambiguous routes because tests happen to pass.

## Own

- `src/chirp/routing/`.
- `tests/test_route.py`, `tests/test_router.py`, `tests/test_params.py`, `tests/test_url_for.py`, `tests/contracts/test_routes.py`.
- Routing docs, named-route RFCs, and routing examples/scaffolds.
