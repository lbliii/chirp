# Epic: Downstream Product Success

**Status**: Draft roadmap, research-sourced
**Updated**: 2026-05-09
**Source**: ELBYSODIC consumer audit, current Chirp roadmap, `forum_shell` fixture, and planning steward guidance
**Target**: Chirp framework support for large server-rendered products
**Not Target**: Building a full forum inside this repository

---

## Product Research Read

ELBYSODIC is already the downstream play-by-post product. Chirp should not
duplicate its domain model, screens, workflows, data schema, or production
roadmap. The useful research signal is where a serious Chirp consumer needs
framework support to keep a large hypermedia product coherent.

The downstream pattern is:

- filesystem pages with deep route hierarchies;
- app-shell navigation with boosted links, OOB shell state, and fragment
  targets;
- tenant-prefixed shared-host URLs;
- login/session/CSRF middleware around server-rendered forms;
- rich multi-intent POST handlers;
- SSE/OOB updates for post-load activity;
- `app.check()` as a startup contract, not a nice-to-have.

## Invariants

- Chirp remains hypermedia-native: no SPA, JSON side channel, or client build
  pipeline to solve product complexity.
- Product code owns product semantics. Chirp owns reusable framework contracts,
  diagnostics, URL/routing primitives, return types, and examples.
- `examples/chirpui/forum_shell` is a compact regression fixture, not a forum
  product seed.
- Any public API, route semantics, middleware behavior, or contract severity
  change needs steward review before implementation.
- Every accepted item needs proof in tests/docs/examples or an explicit
  no-collateral note.

## Ranked Investments

### 1. Mounted Page Contract Confidence

**User problem**: Large products rely on mounted filesystem pages, but route
wrappers, source handlers, terminal checks, and `app.check()` must all agree on
the same contracts.

**Chirp outcome**:
- Treat handler-to-wrapper contract propagation as a supported invariant.
- Keep route explorer, terminal checks, contract coverage, and docs aligned.
- Add regression coverage when product audits reveal a wrapper/source mismatch.

**Required proof**:
- Mounted GET/POST page with `FormContract` counts in contract coverage.
- Route explorer and terminal check output show the same route contract state.
- `examples/chirpui/forum_shell` stays green as downstream-style proof.

**Collateral**: contract docs and `forum_shell` README if behavior or wording
changes.

### 2. Tenant/Base-Path URL Support

**User problem**: Shared-host products need URLs such as
`/c/{community_slug}/boards/...` without regex rewriting rendered HTML or
storing request state in private caches.

**Chirp outcome**:
- Design a request-scoped URL-prefix strategy for `url_for`, redirects, htmx
  attributes, and SSE endpoints.
- Preserve the current app-root `url_for` contract unless an RFC deliberately
  changes it.
- Provide hooks or helper APIs that middleware can use without touching private
  request internals.

**Required proof before implementation**:
- RFC with examples for normal routes, tenant-prefixed routes, redirects,
  query-string `next` values, htmx attributes, and SSE URLs.
- Tests for full page, boosted fragment, redirect, and SSE-link generation.
- Compatibility note for existing `url_for` users.

**Collateral**: routing docs, deployment docs for shared-host apps, examples
only after the API is stable.

### 3. Production Form Ergonomics

**User problem**: Real server-rendered products have many POST forms, repeated
fields, multiple submit intents, safe redirects, CSRF, and validation errors.
The secure path should be natural without requiring regex response rewriting.

**Chirp outcome**:
- Make CSRF helper usage and middleware ordering easy to verify.
- Improve documented patterns for multi-intent forms and repeated fields.
- Consider `app.check()` guidance for POST forms that are likely missing CSRF
  when `CSRFMiddleware` is active.
- Keep automatic mutation of arbitrary HTML out of core unless a design review
  proves it is safe.

**Required proof**:
- Form docs cover login, multi-intent actions, repeated list fields, and
  htmx/non-htmx validation paths.
- Tests exercise `form_from`, `FormContract`, CSRF helpers, and mounted pages
  together.
- Security-sensitive changes get focused middleware tests.

**Collateral**: forms docs, production deployment checklist, examples using
`CSRFMiddleware`.

### 4. App-Shell, OOB, And SSE Hardening

**User problem**: Product shells combine boosted navigation, nested layouts,
OOB theme/sidebar regions, and live updates. A bad swap target or missing OOB
region can blank the main surface or leave stale shell state.

**Chirp outcome**:
- Keep app-shell outlet behavior, OOB registry checks, and fragment/SSE
  contracts low-noise and fail-loud.
- Validate tenant-like path prefixes and boosted navigation in examples or
  contract tests where useful.
- Define replay/event-id guidance before recommending product-critical SSE
  streams.

**Required proof**:
- Contract tests for boosted shell outlet rendering and OOB/SSE coexistence.
- Browser smoke for at least one shell example when changing rendering
  behavior.
- Multi-client/reconnect SSE tests before promoting replay semantics.

**Collateral**: htmx patterns, devtools docs, realtime docs, shell examples.

### 5. Downstream-Grade Diagnostics And Fixtures

**User problem**: Large products need errors that point to the route, block,
selector, middleware, template, or config flag that must change. Examples need
to demonstrate product-shaped contracts without becoming products.

**Chirp outcome**:
- Keep examples small but tied to real failure modes: mounted forms, CSRF,
  shell outlet swaps, OOB regions, SSE, and URL generation.
- Expand contract category docs and terminal output around product-impacting
  checks.
- Add product-research notes when a downstream app exposes a reusable gap.

**Required proof**:
- Docs list emitted contract categories, severity, and fix guidance.
- Example tests cover the intended contract behavior.
- Planning docs distinguish shipped behavior, draft architecture, and
  downstream product ownership.

**Collateral**: `plan/roadmap.md`, examples audit notes, contract docs.

## Not Now

- Building ELBYSODIC or another full forum in this repository.
- Forum-specific CLI generators.
- Generic product schemas, migrations, roles, moderation, or workflow engines.
- Core dependency on `chirp-ui`.
- Automatic response HTML mutation for tenant scoping or CSRF injection without
  an RFC and security review.
- Contract severity promotions without maintainer review.

## Implementation Sequence

1. **Validation confidence gate**: fix broad-test blockers or keep them recorded
   as explicit environment drift. Current blockers are a missing third-party
   pytest plugin module during autoload and installed Kida lacking
   `resolve_template_name`.
2. **RFC 006 decision**: request URL scope RFC exists; next step is choosing
   the public shape and proof matrix, not writing another RFC.
3. **Request URL scope implementation**: keep `app.url_for(...)` deterministic;
   add request-scoped helpers without mutating frozen app state or rendered
   HTML.
4. **Production form integration proof**: verify CSRF, typed binding,
   `FormContract`, repeated fields, multi-intent forms, and htmx/non-htmx
   validation together before adding new checks.
5. **CSRF check decision**: either add a narrow `csrf_form` `app.check()` rule
   gated on `CSRFMiddleware`, or explicitly defer it if scanner noise is too
   high.
6. **Shell/realtime proof**: add reconnect/replay tests and one deterministic
   browser smoke for shell/OOB/SSE behavior. Tenant-like shell proof waits for
   request URL scope.
7. **Diagnostics and fixtures**: keep `forum_shell` narrow and add only the
   smallest fixture or contract test needed for reusable framework gaps.

## Open-Item Steward Synthesis

Consulted stewards: routing/app lifecycle, contracts/forms/security,
realtime/rendering, and planning. A dedicated docs/examples/tests steward did
not return before synthesis; planning reviewed those scoped files, and the
missing dedicated signal is recorded as residual risk.

### Convergence

- `app.url_for(...)` stays app-root deterministic.
- Request URL scope must be request-local, not frozen app state or ambient
  global state.
- Automatic rendered-HTML mutation for tenant URLs or CSRF is not a Chirp core
  pattern.
- `forum_shell` remains a fixture, not a product.
- CSRF missing-field checks are useful only if narrow and low-noise.
- SSE replay is product-owned durable cursor behavior; Chirp should prove
  `Last-Event-ID` handling patterns without adding a queue/store.
- Browser proof is required for shell/OOB/SSE behavior that can pass string
  tests while failing in the live DOM.

### Raw Steward Signals

| Steward | Area | Severity | Accepted Finding | Required Proof | Confidence |
| --- | --- | --- | --- | --- | --- |
| Routing/App | Request URL scope | P1 | Preserve `app.url_for(...)`; add request-aware helper/scope instead | app-root URL tests unchanged; request-scoped template, redirect, htmx, SSE, mount, no-request, and concurrency tests | High |
| Routing/App | Private URL rewriting | P1 | Replace private request/cache and regex HTML rewriting with public request URL scope | Tenant-like fixture with scoped URLs and no rendered HTML mutation | High |
| Routing/App | Mount composition | P2 | Route reversal happens before request scope prefix; route explorer shows app-root paths | `test_mount_app.py` and `test_url_for.py` scoped mount cases | Medium-high |
| Contracts/Forms/Security | CSRF form coverage | P1 | Add a narrow `csrf_form` check only after false-positive review | Missing/present token cases; dynamic/exempt skip cases; htmx header pattern docs | High |
| Contracts/Forms/Security | Mounted `FormContract` | P2 | Keep wrapper/source contract visibility as regression contract | `forum_shell` plus focused mounted POST contract fixture | High |
| Contracts/Forms/Security | Safe redirects | P1 | Strengthen examples/tests for `next=` and local URL safety | `is_safe_url()` tenant/local/evil/encoded cases and login behavior | High |
| Realtime/Rendering | Browser shell proof | P1 | Add one deterministic browser smoke before broader shell claims | Stable SSE listener, boosted navigation, OOB update, no full-document fragment, listener survives navigation | High |
| Realtime/Rendering | Replay/reconnect | P1 | Prove `Last-Event-ID` pattern; product owns durable cursor | Multi-client/reconnect test with missed-event ordering | High |
| Realtime/Rendering | SSE docs drift | P2 | Update docs to match tested production error events | Existing SSE integration tests plus docs link check | High |
| Planning | Roadmap state | P1 | Roadmap must say RFC 006 exists and next step is API decision | Docs link drift check | High |

### Dependencies

- Request URL scope blocks tenant-like shell navigation fixtures.
- CSRF `app.check()` work depends on false-positive review and form integration
  proof.
- Safe redirect guidance depends on request URL scope for tenant-prefixed
  `next` semantics.
- SSE replay promotion depends on durable event-id/reconnect tests.
- Broad examples/browser confidence depends on resolving or explicitly
  documenting current validation environment drift.

### Ranked Backlog

1. Roadmap/RFC status cleanup for RFC 006.
2. Request URL scope API decision.
3. Request URL scope implementation and tests.
4. Production form integration proof.
5. CSRF missing-field `app.check()` RFC or explicit deferral.
6. Safe redirect proof coordinated with URL scope.
7. SSE replay/reconnect proof.
8. Deterministic shell/OOB/SSE browser smoke.
9. Diagnostics/category docs polish.
10. Keep `forum_shell` current as a narrow fixture.

### Minority Reports

- ELBYSODIC can continue product-first work with explicit middleware while
  Chirp designs request URL scope.
- CSRF missing-field checks may remain docs-only if the scanner is too noisy.
- `forum_shell` should not gain tenant behavior until request URL scope is
  stable.

### Not Now

- Tenant router, tenant schema, membership model, or ELBYSODIC-specific policy.
- Automatic rendered-HTML rewriting for tenant URLs or CSRF.
- Ambient request-aware behavior in `app.url_for(...)`.
- `AppConfig` base-path field for per-request tenant prefixes.
- Static source-code analysis for arbitrary safe redirects.
- Replay storage, queues, presence tracking, or forum-specific realtime
  primitives in Chirp.
- Broad app-shell browser suite before one deterministic smoke is stable.

## Open Questions

- Should request-scoped URL prefixing be an app-level feature, middleware hook,
  or explicit helper layered on `url_for`?
- Can CSRF-missing-form checks be useful without excessive false positives in
  apps that intentionally use non-template forms?
- Should `forum_shell` gain tenant-like URL tests, or should that wait until
  the URL-prefix RFC settles?
- Which diagnostics belong in `app.check()` versus DevTools/runtime debug
  surfaces?
