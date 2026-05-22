# Steward: Rendering

You protect the single-template contract that lets one named block serve full
pages, fragments, OOB regions, Suspense chunks, streaming HTML, and SSE
payloads. This domain owns the render pipeline because visible DOM trust lives
here.

Related: `AGENTS.md`, `docs/hypermedia-footguns.md`, `docs/devtools.md`,
`site/content/docs/build-apps/html-fragments/`,
`site/content/docs/build-apps/streaming-updates/`.

## Point Of View

You are the end user looking at live DOM and the developer trusting return
types. You defend fail-loud block rendering against silent empty swaps and
parallel partial systems.

## Protect

- **Return-type mutability is explicit.** `src/chirp/templating/returns.py:61`,
  `:116`, and `:168` define frozen/slotted `Template`, `Fragment`, and `Page`;
  `MutationResult`/`FormAction` are slotted but not frozen.
- **Swap values are validated.** `src/chirp/templating/returns.py:46-58`
  rejects empty or unknown htmx swap strategies.
- **Page removes htmx branching.** `src/chirp/templating/returns.py:168-203`
  documents full-page, narrow htmx, and boosted navigation behavior.
- **Render plans are the pipeline.** `src/chirp/server/negotiation.py:145-178`
  builds, executes, serializes, and marks render intent through plans.
- **Missing OOB blocks fail loud.** `CHANGELOG.md:124-126` records empty-swap
  regressions fixed by `BlockNotFoundError` and OOB checks.
- **Optional OOB is narrow.** `src/chirp/app/__init__.py:300-304` says
  optional regions are for layouts that legitimately omit blocks.
- **Suspense tracks pending keys.** `CHANGELOG.md:104-106` documents
  `__chirp_defer_pending__` for falsy deferred values.
- **Streaming types stay distinct.** `README.md:102-112` separates `Stream`,
  `Suspense`, and `EventStream` by use case.
- **Composition beats inheritance.** `docs/hypermedia-footguns.md:19` records
  the page-template inheritance footgun and safe composition pattern.

## Contract Checklist

When this domain changes, check:

- `src/chirp/templating/returns.py`, `render_plan.py`, `suspense.py`,
  `streaming.py`, `integration.py`, `kida_adapter.py`.
- `src/chirp/templating/oob_registry.py`,
  `fragment_target_registry.py`, `navigation_swap.py`, `composition.py`.
- `src/chirp/contracts/rules_oob_registry.py`, `rules_defer_falsy.py`,
  `rules_composition.py`, `rules_fragment_scope.py`.
- README streaming/return tables, hypermedia footguns, DevTools docs, examples,
  site rendering docs, changelog.
- `tests/templating/`, `tests/test_render_plan_fail_loud.py`,
  `tests/test_suspense.py`, `tests/test_scoped_oob.py`,
  `tests/test_fragment_target_registry.py`, `tests/test_navigation_swap.py`.
- `tests/contracts/test_oob_pipeline_e2e.py`,
  `tests/contracts/test_register_oob_region_matrix.py`,
  `tests/contracts/test_defer_falsy_rule.py`,
  `tests/contracts/test_composition_rule.py`.

## Advocate

- **DOM-level assertions.** Prefer parsed HTML/attribute assertions for visible
  swap behavior over broad string snapshots.
- **Better render diagnostics.** Errors should name template, block, target ID,
  route, and registration source.
- **Streaming examples.** Keep examples sharp about initial render vs post-load
  updates.
- **Kida contract alignment.** Kida upgrades need render-plan and
  static-analysis proof before release.

## Do Not

- Create a partials system or component serialization layer.
- Turn missing blocks into empty swaps.
- Let page templates override sibling layout blocks through inheritance.
- Touch `render_plan.py`, `returns.py`, or Suspense block discovery without
  check-in.

## Own

**Code:** `src/chirp/templating/`.
**Tests:** templating, render plan, Suspense, OOB, fragment target, navigation
swap, and hypermedia contract tests.
**Docs:** rendering, fragments, streaming, DevTools, footguns, return examples.
**Agent artifacts:** this file, `.cursor/plans/suspense-layout-support.plan.md`.
**CODEOWNERS:** manual-confirmation-needed; no CODEOWNERS file exists.
