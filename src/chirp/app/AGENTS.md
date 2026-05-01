# AGENTS.md

## Steward: App Lifecycle Steward

This domain protects `App`: registration, compilation, freezing, runtime state publication,
lifespan hooks, service injection, mounting, URL generation, and the point where setup becomes
immutable runtime.

## Must Not Become

- A mutable runtime registry after freeze.
- A grab bag for request handling details that belong in `server`.
- A place where contract checks can observe half-published state.

## Documentation Ownership

Update README, `docs/public-api.md`, `docs/routing/mounting.md`, and release notes when app methods,
mount behavior, lifecycle hooks, or config binding change.

## Local Checks

Start with:

- `uv run pytest tests/test_app tests/test_app_bind_config.py tests/test_mount_app.py -q`
- `uv run pytest tests/test_url_for.py tests/test_route_meta.py tests/test_page_handler_check.py -q`
- `uv run pytest tests/test_concurrency/test_oob_registry_contention.py -q` when registry state changes

## Public Contracts And Safety Boundaries

- `App` is mutable only during setup. Freeze is a lifecycle boundary, not an optimization detail.
- Contract checks must run after runtime state is ready in debug startup/freeze paths.
- Public `App` methods are stable API; new methods or changed semantics need docs and changelog.
- Shared state must be frozen, copy-on-write, or protected by a clear lock.
