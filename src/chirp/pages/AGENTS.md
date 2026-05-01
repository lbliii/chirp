# AGENTS.md

## Steward: Filesystem Pages And Shell Steward

This domain protects page directory discovery, `_meta.py`, `_context.py`, `_actions.py`, sections,
shell regions, shell actions, layout chains, and reactive page helpers.

## Must Not Become

- A second template renderer; rendering belongs in `templating`.
- A router that bypasses `routing` contracts.
- A shell system that lets broad inherited htmx targets erase user-visible UI.

## Documentation Ownership

Update README feature tables, route-directory docs, shell/action examples, and scaffold docs when
page conventions or shell behavior change.

## Local Checks

Start with:

- `uv run pytest tests/test_page_resolve.py tests/test_page_discovery_names.py -q`
- `uv run pytest tests/test_route_directory_contract_e2e.py tests/test_shell_actions.py tests/test_shell_regions.py -q`
- `uv run pytest tests/test_reactive_register.py tests/test_reactive_stream.py tests/contracts/test_reactive.py -q`

## Public Contracts And Safety Boundaries

- Page conventions are executable documentation; examples and scaffolds must stay aligned.
- Shell regions and actions affect OOB swaps and broad navigation targets; prefer fail-loud checks.
- Reactive shared state needs an explicit free-threading story and stress coverage.
