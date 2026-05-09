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

1. **Plan cleanup**: mark the old PBP forum plan as superseded by downstream
   product research; keep useful framework observations.
2. **Contract confidence pass**: audit mounted-page contract propagation,
   route explorer output, terminal checks, and `forum_shell`.
3. **Forms/docs pass**: update production form guidance around CSRF,
   multi-intent forms, repeated fields, and mounted page contracts.
4. **Tenant URL RFC**: design request-scoped URL prefix support before code.
5. **Shell/realtime proof**: continue browser and contract proof for app-shell,
   OOB, and SSE behavior.

## Open Questions

- Should request-scoped URL prefixing be an app-level feature, middleware hook,
  or explicit helper layered on `url_for`?
- Can CSRF-missing-form checks be useful without excessive false positives in
  apps that intentionally use non-template forms?
- Should `forum_shell` gain tenant-like URL tests, or should that wait until
  the URL-prefix RFC settles?
- Which diagnostics belong in `app.check()` versus DevTools/runtime debug
  surfaces?
