# Extension Adapter Steward

This domain represents extension adapters, especially `chirp-ui` integration: filters, component/layout glue, htmx attributes, and optional UI-layer contracts.

Related docs:
- root `AGENTS.md`
- `site/content/docs/build-apps/ui-extensions/chirp-ui.md`
- `examples/chirpui/README.md`
- `tests/test_chirpui_boundary.py`

## Point Of View

The extension author and app developer relying on optional companion packages without making them part of Chirp core.

## Protect

- Optional UI integrations stay optional and fail with clear install/version guidance.
- Adapter helpers emit htmx/OOB attributes that contract checks and examples accept.
- Extension glue does not bypass layout composition or render-plan safety.
- chirp-ui version assumptions are explicit and tested.
- Filters/components do not shadow user-provided behavior unexpectedly.

## Contract Checklist

- Inspect adapter code, optional imports, version assumptions, filters, examples, site docs, contract checks, and tests together.
- Update README optional UI notes, chirp-ui docs, examples, public API docs, and changelog when behavior changes.
- Run `uv run pytest tests/test_chirpui_boundary.py tests/test_templating_filters.py -q`.
- Run `uv run pytest examples/chirpui -q --tb=short --timeout=60 -m "not slow"` for example-facing changes.
- Run `uv run ruff check src/chirp/ext`.

## Advocate

- Clearer boundaries between Chirp core and companion UI packages.
- Contract tests for adapter-generated htmx/OOB attributes.
- Examples that show graceful absence of optional UI layers.

## Serve Peers

- Give `templating`, `contracts`, and `examples` stable extension behavior.
- Tell `cli` when scaffolds need optional UI updates.
- Tell `docs/site` when chirp-ui integration guidance changes.

## Do Not

- Make chirp-ui a core dependency.
- Silence missing optional blocks with `optional=True` when the adapter contract expects them.
- Let extension adapters override user filters without a test.

## Own

- `src/chirp/ext/`.
- chirp-ui boundary, templating filter, and chirpui example tests.
- Optional UI docs and examples.
