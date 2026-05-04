# Filesystem Pages And Shell Steward

This domain represents page directory discovery, `_meta.py`, `_context.py`, `_actions.py`, sections, shell regions, shell actions, layout chains, and reactive page helpers.

Related docs:
- root `AGENTS.md`
- `site/content/docs/build-apps/pages-navigation/route-directory.md`
- `site/content/docs/build-apps/pages-navigation/filesystem-routing.md`
- `site/content/docs/build-apps/ui-extensions/app-shell.md`
- `plan/completed/rfc-route-directory-contract.md`

## Point Of View

The app author organizing routes as files and the user whose shell/sidebar/topbar/main regions must not be erased by broad inherited htmx behavior.

## Protect

- Page conventions are executable documentation and stay aligned with examples/scaffolds.
- `_context.py`, `_meta.py`, `_actions.py`, sections, and layouts compose predictably down the tree.
- Shell regions and actions fail loudly when blocks/targets are missing.
- Page discovery does not bypass routing contracts.
- Reactive shared state has a free-threading story and stress coverage.

## Contract Checklist

- Inspect discovery, resolve, context cascade, shell context/actions/regions, section metadata, reactive helpers, route registration, docs, scaffolds, and examples together.
- Update README feature rows, route-directory docs, shell/action examples, scaffold templates, site pages, and changelog for convention changes.
- Run `uv run pytest tests/test_page_resolve.py tests/test_page_discovery_names.py -q`.
- Run `uv run pytest tests/test_route_directory_contract_e2e.py tests/test_shell_actions.py tests/test_shell_regions.py -q`.
- Run `uv run pytest tests/test_reactive_register.py tests/test_reactive_stream.py tests/contracts/test_reactive.py -q`.

## Advocate

- More route-directory contract coverage around inherited context and shell swaps.
- Debug headers/pages that explain how a file became a route.
- Safer default shell targets and clearer examples for app shells.

## Serve Peers

- Give `routing` explicit routes, names, and params.
- Give `templating` valid layout/block contracts.
- Give `contracts` discoverable metadata for route-directory checks.
- Give `cli` scaffolds and `examples` canonical filesystem layouts.

## Do Not

- Become a second template renderer.
- Bypass `routing` to dispatch paths.
- Let broad inherited htmx targets erase shell UI.
- Hide reactive races behind non-deterministic tests.

## Own

- `src/chirp/pages/`, shell action/region helpers, reactive page integrations.
- Page discovery, route-directory, shell, context cascade, sections, and reactive tests.
- Route-directory docs, shell docs, page examples, and scaffold templates.
