# Plan: 1.0 Public Surface Audit

**Status**: Completed initial audit
**Created**: 2026-05-03
**Completed**: 2026-05-03
**Target**: last pre-1.0 minor before the 1.0 compatibility declaration
**Steward**: Narrative Docs Steward + Public Surface Steward

---

## Audit Result

The initial export audit is complete for the current top-level surface:

- `chirp.__all__`, `_LAZY_IMPORTS`, and `_API_STATUS` are covered by
  `tests/test_lazy_imports.py`.
- `JSONResponse` is promoted to stable to match the documented HTTP surface and
  current example usage.
- No provisional export should be removed from the top-level path in this pass.
- No other provisional export should be promoted before 1.0 without a focused
  hardening PR and documentation update.

## Recommendation

Do not move Chirp to 1.0 by changing the classifier alone. Treat 1.0 as a
compatibility promise over the current stable surface, after each provisional
area has an explicit decision: stabilize, keep provisional with a narrow reason,
or hide behind a more specific module-level API.

## Current Baseline

`docs/public-api.md` already separates stable, provisional, debug/advanced, and
internal names. That split is the right shape for 1.0. The audit should preserve
the everyday route-author surface while forcing decisions on extension and
diagnostic APIs.

## Stabilize Unless Evidence Says Otherwise

These areas are already documented as stable and are central to the framework's
identity:

| Area | Decision |
|------|----------|
| Application | Keep `App` and `AppConfig` stable; avoid new config fields during the audit unless they remove an existing ambiguity. |
| Return types | Keep the current return-type set stable. New return types stay out of scope for 1.0. |
| HTTP basics | Keep `Request`, `Response`, `JSONResponse`, `Redirect`, and `hx_redirect` stable. |
| Middleware protocol | Keep `Middleware`, `Next`, and `AnyResponse` stable if the type checks and examples still exercise the intended shape. |
| Forms and security helpers | Keep stable, but verify optional-extra behavior and error messages before 1.0. |

## Decision Queue

These provisional areas need explicit 1.0 decisions:

| Area | Default Decision | Reason |
|------|------------------|--------|
| Contracts | Keep provisional through 1.0 unless plugin authors need a hard compatibility promise. Contract categories and severities are still active design space. |
| Suspense template sentinels | Keep provisional. They expose render-pipeline internals for templates and checks. |
| HTMX details | Consider stabilizing `HtmxDetails`; keep `STOP_POLLING` provisional unless the SSE/polling contract is fully documented. |
| Reactive pages | Keep provisional until free-threading stress coverage and user-facing examples settle. |
| Shell actions | Keep provisional unless the ChirpUI app-shell contract is declared stable in both repos. |
| Tools | **Stabilized (2026-06-22)** — Phase 1 (#421/#430): registry, MCP server, event bus, OTel spans, and tests meet the stable bar. |
| Cache helpers | Keep provisional until backend behavior, cache key semantics, and streaming bypass behavior are documented as public contracts. |
| Optional UI bridge | Keep provisional because it depends on `chirp-ui` compatibility and manifest behavior outside this package. |
| Render planning / composition / navigation swaps | Keep debug/advanced, not stable. These are diagnostics and framework tooling surfaces. |

## Completed Audit Tasks

1. Snapshot `chirp.__all__`, `_API_STATUS`, and `docs/public-api.md` side by
   side. Every exported name must have a tier and a reason to keep that tier.
2. For every stable name, verify there is at least one public-path test or
   example covering the behavior app authors depend on.
3. For every provisional name, choose one of: stabilize, keep provisional with a
   documented reason, or move out of the top-level export path before 1.0.

## Completed Follow-Ups

1. Review `AppConfig` for fields that are accidental policy rather than stable
   configuration. Result: no pre-1.0 removal or rename in this pass; field-level
   stability is documented in `docs/plan-appconfig-1-0-audit.md`.
2. Review error messages for top-level stable APIs. Result: the initial pass is
   documented in `docs/plan-stable-error-message-audit.md`; routing, forms, and
   session messages received focused actionability fixes.

## Remaining Follow-Ups

1. Run release gates and examples after any tier change.

## 1.0 Non-Goals

- No new return type.
- No new mandatory runtime dependency.
- No broad render-pipeline refactor.
- No marketing claim that "mature" means "finished."
- No demotion of existing contract errors without a migration note and reviewer
  sign-off.

## Exit Criteria

- `docs/public-api.md` is current and every provisional name has an intentional
  reason.
- Any stable API break has a deprecation path or a documented pre-1.0 migration
  note.
- Release gates in `docs/release-policy.md` pass.
- README and package classifier agree with the chosen maturity claim.
- The 1.0 release notes say what is stable, what remains provisional, and why.
