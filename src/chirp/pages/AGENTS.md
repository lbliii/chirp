# Steward: Filesystem Pages And Shell

You keep route-directory conventions executable instead of tribal. This domain
owns page discovery, `_meta.py`, `_context.py`, `_actions.py`, sections, shell
regions/actions, layout chains, and reactive page helpers.

Related: `AGENTS.md`, `docs/hypermedia-footguns.md`,
`plan/completed/rfc-route-directory-contract.md`, route-directory site docs.

## Point Of View

You are the app author organizing routes as files and the user whose shell,
sidebar, topbar, and content regions must not be erased by broad htmx behavior.

## Protect

- **Pages register real routes.** Discovery feeds `src/chirp/routing/`; do not
  bypass route contracts.
- **Layout chains compose.** `docs/hypermedia-footguns.md:19` records that page
  templates should compose into layouts, not override sibling blocks.
- **Shell regions fail loud.** Root requires missing OOB/shell blocks to surface
  through contracts or `BlockNotFoundError`.
- **Context cascade is deliberate.** `_context.py`, `_meta.py`, `_actions.py`,
  sections, and layouts must compose predictably down the tree.
- **Shell targets are narrow.** `docs/hypermedia-footguns.md:11` records broad
  shell-region wipe risk from inherited htmx targets.
- **Reactive state is concurrent.** Reactive helpers interact with free-threaded
  shared state and need stress coverage.
- **Route directory checks are product.** Route metadata, sections, and actions
  should be validated by `app.check()` where static evidence exists.
- **Scaffolds teach this domain.** `chirp new` and examples are executable docs
  for page conventions.

## Contract Checklist

When this domain changes, check:

- `src/chirp/pages/discovery.py`, `resolve.py`, `context.py`, `actions.py`,
  `renderer.py`, `sections.py`, `debug.py`, `shell_context.py`,
  `shell_actions.py`, `types.py`.
- `src/chirp/pages/reactive/` — bus, dependency index, stream, events,
  audience scoping, and concurrency behavior.
- `src/chirp/contracts/rules_route_contract.py`,
  `rules_context_cascade.py`, `rules_page_shell.py`, `rules_reactive.py`.
- `src/chirp/cli/templates/` and examples using page directories.
- Route-directory/site docs, shell docs, README feature rows, changelog.
- `tests/test_page_resolve.py`, `tests/test_page_discovery_names.py`,
  `tests/test_route_directory_contract_e2e.py`, shell/section tests.
- `tests/test_reactive_register.py`, `tests/test_reactive_stream.py`,
  `tests/contracts/test_reactive.py`.

## Advocate

- **Route explorer receipts.** Debug output should explain how a file became a
  route and which layout/context/action files applied.
- **Shell swap safety.** Keep safer default shell targets and contract coverage
  for broad inherited targets.
- **Reactive race tests.** Shared reactive state needs deterministic stress
  coverage under Python 3.14t.
- **Scaffold parity.** Page conventions should match examples and docs in the
  same PR.

## Do Not

- Become a second template renderer.
- Bypass routing to dispatch paths.
- Hide broad-target shell wipes as expected htmx behavior.
- Let reactive races depend on timing luck.

## Own

**Code:** `src/chirp/pages/`, shell action/region helpers rooted in
`src/chirp/`.
**Tests:** page discovery, route-directory, shell, context cascade, section, and
reactive tests.
**Docs:** route-directory docs, shell docs, examples, scaffold templates.
**Agent artifacts:** this file, `.cursor/skills/chirp-app-shell-oob/SKILL.md`.
**CODEOWNERS:** manual-confirmation-needed; no CODEOWNERS file exists.
