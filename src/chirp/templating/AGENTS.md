# Rendering Steward

This domain represents template return types, Kida integration, render plans, OOB registries, fragment targets, navigation swaps, streaming HTML, and Suspense.

Related docs:
- root `AGENTS.md`
- `docs/hypermedia-footguns.md`
- `docs/devtools.md`
- `site/content/docs/build-apps/html-fragments/`
- `site/content/docs/build-apps/streaming-updates/`

## Point Of View

The end user looking at live DOM and the app developer who trusts a single template/block contract to render every access pattern safely.

## Protect

- Missing OOB blocks fail loudly with actionable `BlockNotFoundError` detail.
- Suspense preserves `None` placeholders and handles falsy resolved values correctly.
- `Stream`, `Suspense`, and `EventStream` keep distinct jobs.
- Render plans prune only safe ancestors and never emit swaps for non-existent targets.
- Page templates do not escape composition by extending registered layouts.

## Contract Checklist

- Inspect `returns.py`, `render_plan.py`, `suspense.py`, OOB/fragment registries, Kida adapter, filters, streaming, and navigation swaps together.
- Update README, hypermedia footguns, DevTools, site rendering docs, examples, and changelog for return-type/render behavior changes.
- Run `uv run pytest tests/templating tests/test_render_plan_fail_loud.py tests/test_suspense.py -q`.
- Run `uv run pytest tests/test_scoped_oob.py tests/test_fragment_target_registry.py tests/test_navigation_swap.py -q`.
- Run `uv run pytest tests/contracts/test_oob_pipeline_e2e.py tests/contracts/test_defer_falsy_rule.py -q`.

## Advocate

- More contract tests around realistic DOM swaps instead of raw string snapshots.
- Render diagnostics that name template, block, target ID, and registration.
- Better examples distinguishing streaming types and OOB region safety.

## Serve Peers

- Give `server` deterministic render results and loud exceptions.
- Give `contracts` metadata for block, layout, OOB, Suspense, and composition checks.
- Give `pages`, `examples`, and `site` safe patterns for layouts and fragments.

## Do Not

- Create a partials system or component serialization layer.
- Turn missing blocks into empty swaps.
- Let page templates override sibling layout blocks through inheritance.
- Touch render pipeline invariants without check-in.

## Own

- `src/chirp/templating/`.
- Templating, render plan, Suspense, OOB, fragment target, navigation swap, and hypermedia contract tests.
- Rendering docs, streaming docs, DevTools docs, and examples showing return types.
