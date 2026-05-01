# AGENTS.md

## Steward: Rendering Steward

This domain protects template return types, Kida integration, render plans, OOB registries,
fragment targets, navigation swaps, streaming HTML, and Suspense.

## Must Not Become

- A partials system or component serialization layer.
- A permissive renderer that turns missing blocks into empty swaps.
- A place where page templates can escape the composition model by extending layouts.

## Documentation Ownership

Update README, `docs/hypermedia-footguns.md`, `docs/devtools.md`,
`site/content/docs/guides/render-plan.md`, and examples when return types or render behavior change.

## Local Checks

Start with:

- `uv run pytest tests/templating tests/test_render_plan_fail_loud.py tests/test_suspense.py -q`
- `uv run pytest tests/test_scoped_oob.py tests/test_fragment_target_registry.py -q`
- `uv run pytest tests/contracts/test_oob_pipeline_e2e.py tests/contracts/test_defer_falsy_rule.py -q`

## Public Contracts And Safety Boundaries

- Missing OOB blocks should fail loudly with actionable `BlockNotFoundError` detail.
- Suspense must preserve `None` placeholders and handle falsy resolved values correctly.
- Render plan changes need end-to-end contract coverage, not only unit tests.
- Touching `render_plan.py`, `returns.py`, or Suspense discovery is an escape-hatch check-in.
