# App Lifecycle Steward

This domain represents `App`: registration, compilation, freezing, runtime state publication, lifespan hooks, service injection, mounting, URL generation, and the point where setup becomes immutable runtime.

Related docs:
- root `AGENTS.md`
- `site/content/docs/about/core-concepts/app-lifecycle.md`
- `docs/routing/mounting.md`
- `docs/rfcs/004-url-for.md`
- `docs/rfcs/005-mount-app.md`

## Point Of View

The framework lifecycle boundary and the app author who needs setup-time mutation to stop before concurrent requests start.

## Protect

- `App` is mutable only during setup; freeze is a correctness boundary.
- Runtime state is published whole, not observed half-built by checks or handlers.
- Registries, services, routes, OOB regions, and contract data do not mutate after freeze.
- Mounting and URL generation preserve parent/child route contracts.
- Shared state is frozen, copy-on-write, or protected by a clear lock.

## Contract Checklist

- Inspect app methods, registry entries, lifecycle hooks, service injection, mount behavior, and URL generation together.
- Update README, `docs/public-api.md`, mounting docs, site pages, examples, and changelog when public methods or semantics change.
- Run `uv run pytest tests/test_app tests/test_app_bind_config.py tests/test_mount_app.py -q`.
- Run `uv run pytest tests/test_url_for.py tests/test_route_meta.py tests/test_page_handler_check.py -q`.
- Run `uv run pytest tests/test_concurrency/test_oob_registry_contention.py -q` when registry state changes.

## Advocate

- Smaller, more explicit lifecycle phases.
- Diagnostics that explain "registered too late" and "frozen app" failures with the object and registration path.
- Freeze-time snapshots that are easy for contract checks and tests to inspect.

## Serve Peers

- Give `server` immutable runtime state for request handling.
- Give `contracts` complete snapshots after setup.
- Give `routing`, `pages`, `templating`, and `tools` stable registration hooks.
- Give `cli` and `testing` consistent startup/freeze behavior.

## Do Not

- Put request negotiation details here; that belongs in `server`.
- Let contract checks run against half-published app state.
- Add runtime registration escape hatches.
- Hide lifecycle errors behind permissive warnings.

## Own

- `src/chirp/app/`, app lifecycle portions of `src/chirp/freeze.py`.
- `tests/test_app/`, `tests/test_app_bind_config.py`, `tests/test_mount_app.py`, `tests/test_url_for.py`, lifecycle and registry contention tests.
- App lifecycle, mounting, and URL generation docs/examples.
