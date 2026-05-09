# Chirp Roadmap

**Status**: Active roadmap synthesis  
**Updated**: 2026-05-09  
**Source**: `plan/drafted/`, release-readiness notes, code/test audit, ELBYSODIC consumer research, and affected steward guidance

---

## Current Read

The roadmap is not empty, but the planning shelf had drifted. Several files in
`plan/drafted/` now describe work that has landed in code and tests, while the
true open work is narrower:

| Plan | Roadmap Status | Evidence |
| --- | --- | --- |
| `epic-agent-vibe-dx.md` | Implemented, historical review record | README validation row, return-type docs, Alpine CDN rule, defer-falsy rule, composition rule, and tests exist |
| `epic-fragment-only-sse.md` | Mostly implemented; remaining work is example/browser audit | `rules_sse` infers literal events, fragment-block tests exist, current status section already notes follow-through |
| `epic-harden-bsite-discoveries.md` | Implemented hardening record | guarded `make_route_link_attrs`, cross-shell/swap tests, `defer_blocks` validation, `swap_attrs` no-context test exist |
| `epic-reactive-phase2.md` | Implemented, with product validation still needed | `ConnectionInfo`, audience filtering, presence, inverse dependency queries, contract checks, and `reactive_tasks` example exist |
| `rfc-alpine-data-helper.md` | Implemented | `alpine_json_config` code, docs, and tests exist |
| `rfc-contract-extensions.md` | Mostly complete; blocked item remains | dead templates, form contracts, SSE contracts, and component-call adapter coverage exist; true typed component validation remains tied to Kida/chirp-ui metadata |
| `rfc-unreachable-block-detection.md` | Implemented | `rules_unreachable_blocks.py`, checker wiring, contract tests, and fragment-block regression tests exist |
| `rfc-shared-store.md` | Phase 1 implemented; later client-store phases deferred | `DeferredCache` exists as the server-side deferred-value cache; no `chirp.stores` client persistence or SSE broadcast store exists |
| `rfc-component-collection.md` | Not now | Separate `chirp-ui` package scope; still blocked on mature typed component contracts |
| `epic-pbp-forum-mvp.md` | Superseded historical product draft | ELBYSODIC is the downstream forum/product; do not rebuild it in Chirp |
| `epic-downstream-product-success.md` | Active product-research roadmap | ELBYSODIC shows reusable framework needs: mounted contracts, tenant URL support, forms/CSRF, shell/OOB/SSE hardening, and diagnostics |

## Ranked Roadmap

### 0. Planning Hygiene And Release Ground Truth

**Why now**: The largest risk is not missing ideas; it is treating historical
plans as active work. That wastes implementation time and causes agents to
rebuild shipped features.

**Scope**:
- Keep this file as the active planning index.
- Add status notes to implemented drafted plans.
- Move or copy implemented plans into `plan/completed/` only when links and
  release notes are checked.
- Keep release-readiness evidence separate from roadmap intent.

**Required proof**:
- `uv run pytest tests/docs/test_site_link_drift.py -q` after moving files.
- `rg "Status.*Draft" plan/drafted` shows only genuinely open drafts.

**Collateral**: `plan/`, `docs/AGENTS.md` if planning policy changes.

### 1. Fragment/SSE Example Audit And Browser Smoke

**Why now**: The fragment/SSE work is mostly implemented, but the remaining
failure mode is user-visible DOM behavior. This is the last high-confidence
follow-through before calling the plan complete.

**Scope**:
- Audit examples for stale `sse-swap="fragment"` and old fragment-only
  workarounds.
- Verify `returns_gallery`, `standalone/sse`, `reactive_tasks`, and one
  ChirpUI shell example in a browser.
- Update example READMEs where the vocabulary should now be "fragment block"
  rather than `fragment_only`.

**Required proof**:
- `uv run pytest tests/contracts/test_sse.py tests/templating/test_fragment_blocks.py -q`
- `uv run pytest examples/standalone/returns_gallery examples/standalone/sse examples/standalone/reactive_tasks -q --tb=short`
- Browser smoke notes or screenshots for at least the gallery and one
  realtime example.

**Collateral**: examples, README/site streaming docs, changelog if behavior or
documented guidance changes.

### 2. Contract And Reactive Docs Parity

**Why now**: The checker and reactive APIs have outpaced the public docs. That
is a roadmap bug because the next product work will copy the docs before it
reads the code.

**Scope**:
- Expand contract-debugging docs into a category reference for shipped
  categories such as `unreachable_block`, `composition_extends`,
  `alpine_cdn_url`, `defer_falsy`, `dead`, `component`, and `form`.
- Add severity, fix guidance, and `override_contract_severity()` examples
  where relevant.
- Update reactive docs for `ConnectionInfo`, `audience`, `presence()`,
  `connection=`, `on_disconnect`, changed-path context builders, and
  `reactive_*` contract metadata.
- Refresh `examples/standalone/reactive_tasks/README.md` and add a 2026
  section to `examples/AUDIT.md` for `forum_shell`, reactive
  presence/audience, fragment blocks, and production-readiness caveats.
- Add or confirm an app.check integration proof for unreachable page blocks
  through real page/layout discovery, then settle the empty-block noise policy.

**Required proof**:
- `uv run pytest tests/docs -q`
- `uv run pytest tests/docs/test_site_link_drift.py -q`
- `uv run pytest tests/contracts/test_unreachable_blocks.py -q`
- `uv run pytest examples/standalone/reactive_tasks examples/chirpui/forum_shell -q --tb=short --timeout=60 -m "not slow"`
- `rg` check that every shipped contract category documented in the site
  category reference is still emitted or mapped by checker/terminal output.

**Collateral**: site contract docs, reactive system docs, `examples/AUDIT.md`,
`reactive_tasks` README, and hypermedia footguns if category guidance changes.

### 3. Downstream Product Success: Mounted Page Contract Confidence

**Why now**: ELBYSODIC shows that a serious product leans on filesystem pages,
generated route wrappers, `FormContract`, route inspection, and `app.check()`.
Those surfaces must agree before deeper product-scale guidance is credible.

**Scope**:
- Audit mounted page contract propagation from source handlers to wrappers.
- Confirm route explorer, terminal checks, contract coverage, and
  `check_hypermedia_surface()` report the same contract state.
- Keep `examples/chirpui/forum_shell` as a compact downstream-style regression
  fixture, not a product template.
- Remove or document any stale guidance that tells agents to build a full forum
  in this repository.

**Required proof**:
- `uv run pytest tests/contracts/test_forms.py tests/contracts/test_form_routes.py -q`
- `uv run pytest examples/chirpui/forum_shell -q --tb=short --timeout=60 -m "not slow"`
- A focused route/terminal check test if the audit finds disagreement.

**Collateral**: `plan/drafted/epic-downstream-product-success.md`, contract
docs if behavior or terminal wording changes, `forum_shell` README if example
positioning changes.

### 4. Downstream Product Success: Request URL Scope Decision

**Why next**: ELBYSODIC currently scopes shared-host community URLs with request
path rewriting and rendered HTML URL rewriting. RFC 006 now exists; the next
roadmap step is to settle its API shape and proof matrix before code.

**Scope**:
- Update RFC 006 from "design sketch" to an implementation-ready decision.
- Preserve `app.url_for(...)` as app-root deterministic.
- Decide whether the first public shape is `request.scoped_url(path)`,
  `request.url_for(...)`, a middleware URL-scope provider, or a combination.
- Define ordering for `mount_app()` plus scoped URLs: route reversal first,
  request scope prefix second.
- Reject automatic rendered-HTML rewriting as a core pattern.

**Required proof before code**:
- Existing `tests/test_url_for.py` stays unchanged.
- Planned tests cover request-scoped template URL generation, redirects and
  `next`, htmx attrs, SSE endpoint attrs, nested `mount_app()`, mounted pages,
  concurrent requests with different prefixes, and no active request/background
  render behavior.
- Route explorer continues to show app-root paths; scoped URL behavior is
  documented separately.

**Collateral**: RFC 006, RFC 004 root-path note if superseded, routing docs,
deployment docs for shared-host apps after implementation.

### 5. Downstream Product Success: Production Form Proof And CSRF Decision

**Why next**: Real Chirp products have many server-rendered POST forms with
repeated fields, multiple submit intents, safe redirects, CSRF, and validation.
ELBYSODIC’s product code proves the need without requiring Chirp to own the
product workflows.

**Scope**:
- Add or confirm integrated proof that `CSRFMiddleware`, `csrf_field()`,
  mounted `FormContract`, `form_from()`, repeated fields, multi-intent forms,
  and htmx/non-htmx validation work together.
- Decide separately whether a narrow `csrf_form` `app.check()` rule is worth
  adding. It should activate only when `CSRFMiddleware` is registered and start
  conservative because false positives are likely.
- Strengthen safe redirect examples and tests, coordinated with URL scope.
- Keep automatic response mutation for CSRF injection out of core unless an RFC
  and security review prove it safe.

**Required proof**:
- `tests/test_csrf.py`
- `tests/contracts/test_forms.py`
- `tests/contracts/test_form_routes.py`
- Focused mounted-page form contract visibility test.
- `is_safe_url()` cases for tenant-prefixed paths, `//evil.com`, schemes,
  empty strings, encoded paths, and login fallback behavior.
- If `csrf_form` is accepted: tests for missing token, present `csrf_field()`,
  present `_csrf_token`, dynamic/exempt forms skipped, and documented htmx
  header patterns not over-enforced.

**Collateral**: forms docs, production deployment checklist, hypermedia
footguns if guidance changes.

### 6. Downstream Product Success: App-Shell, OOB, And SSE Proof

**Why next**: Product shells combine boosted navigation, layout outlets, OOB
theme/sidebar regions, and live updates. A bad contract here blanks visible
content or leaves stale shell state.

**Scope**:
- Continue hardening app-shell outlet selection and OOB registry checks.
- Keep fragment/SSE contracts aligned with DevTools debugging guidance.
- Add explicit reconnect proof before promoting production-critical SSE
  guidance: products own durable cursors; Chirp formats `SSEEvent(id=...)`.
- Update stale SSE docs where they disagree with tested per-event error
  behavior.
- Keep EventStream guidance clear: post-load updates only, not first paint.
- Add tenant-like shell navigation proof only after request URL scope lands.

**Required proof**:
- `uv run pytest tests/contracts/test_shell_outlet_boosted_navigation.py tests/contracts/test_oob_pipeline_e2e.py -q`
- `uv run pytest tests/test_sse_integration.py tests/contracts/test_sse.py -q`
- Multi-client/reconnect test using `Last-Event-ID`.
- Browser smoke for at least one shell example when rendering behavior changes.
- Browser smoke should prove stable `sse-connect`, boosted navigation across
  two pages, OOB shell update, no full-document fragment response, and listener
  survival after navigation.

**Collateral**: htmx patterns, devtools docs, realtime docs, shell examples.

### 7. Downstream Product Success: Diagnostics And Fixtures

**Why later**: Once the contract surface is clearer, Chirp should make product
failures obvious through examples, terminal output, and docs. The point is
small, high-signal fixtures that encode real downstream risks without becoming
full applications.

**Scope**:
- Expand contract category docs with emitted categories, severity, and fix
  guidance.
- Keep `forum_shell` as a compact product-shaped fixture for mounted pages,
  forms, app shell, OOB, and data islands.
- Add or refresh examples only when they prove a framework contract.
- Record downstream product-research findings in planning docs before turning
  them into API work.

**Required proof**:
- `uv run pytest tests/docs -q`
- `uv run pytest tests/docs/test_site_link_drift.py -q`
- Example tests cover every fixture behavior claimed in README prose.

**Collateral**: examples audit notes, contract docs, roadmap updates.

### 8. Component Collection And Component-Call Contracts

**Why later**: This remains ecosystem work, not core framework work. It is also
coupled to typed component metadata in Kida and the separate `chirp-ui`
package. Forcing it into core now would violate the optional-extension boundary.

**Scope**:
- Keep `rfc-component-collection.md` as a not-now ecosystem plan.
- Keep `rfc-contract-extensions.md` Phase 4 blocked until typed component call
  metadata is stable.
- Continue hardening `use_chirp_ui()` as an adapter, not a core dependency.

**Required proof**:
- Kida typed `{% def %}` support or equivalent manifest metadata.
- `uv run pytest tests/test_chirpui_boundary.py tests/test_templating_filters.py -q`
- `uv run pytest examples/chirpui -q --tb=short --timeout=60 -m "not slow"`

**Collateral**: chirp-ui docs, optional UI docs, public API status for
`use_chirp_ui` if its contract changes.

## Steward Synthesis

Accepted findings:

| Steward | Accepted Priority | Rationale |
| --- | --- | --- |
| Planning/docs | Clean stale drafted status before new roadmap work | Prevents historical plans from being mistaken for open work |
| Planning/docs | Reframe forum work as downstream product research | ELBYSODIC owns the product; Chirp owns reusable support surfaces |
| Contracts | Finish proof/collateral for contract-heavy plans before adding new checks | `app.check()` must stay actionable, fast, and low-noise |
| Rendering | Close fragment/SSE example audit before changing Suspense again | The visible DOM contract is the user-facing risk |
| Realtime/server | Validate implemented reactive features in a real app | Per-event and disconnect boundaries need product pressure |
| Realtime/server | Define replay/event-id semantics before forum realtime | Users can miss posts after tab sleep or network blips without a replay contract |
| Data/security/pages | Put product work after framework surfaces are stable | Forum auth/data/page flows are higher risk than examples |
| Extensions/CLI/examples | Keep chirp-ui/component work optional and documented | Avoid making optional UI packages part of Chirp core |
| Benchmarks | Require evidence for hot-path or sync-path changes | Roadmap items here are mostly not performance-sensitive yet |

Deferred findings:
- Shared-store Phase 2 Alpine persistence and Phase 3 SSE broadcast are deferred
  until `DeferredCache` has real downstream use.
- Full PBP moderation, full-text search, rich editor, uploads, theming,
  workflow engines, and product schemas belong to ELBYSODIC or another product,
  not Chirp core.
- Component collection and component-call validation wait for typed component
  metadata.
- `app.check()` large-template timing proof is tracked under contract docs
  parity, but does not block product work unless startup checks regress.

Minority reports:
- A product-first path can continue in ELBYSODIC before Chirp lands tenant URL
  support. That is viable when product-owned middleware remains explicit and
  tested.
- A stricter cleanup path could move all implemented plans out of
  `plan/drafted/` immediately. This roadmap keeps status-note cleanup first so
  link drift can be checked before file moves.

## Parity Matrix

| Contract | API/CLI | Programmatic | Protocol | Schema/Types | Docs | Examples | Tests |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Planning hygiene | No CLI change | No runtime change | No protocol change | No type change | Update `plan/` index and statuses | No example change | Link drift if moving files |
| Fragment/SSE audit | No CLI change | Existing return types only | SSE `message` and fragment-block behavior | No new types | Streaming and fragment docs may need wording | Gallery/SSE/reactive examples | Contract, templating, browser smoke |
| Contract/reactive docs parity | `chirp check` docs only | Existing check/reactive APIs | No protocol change | No type change | Category and reactive guides | Reactive/product-shaped examples | Docs, contracts, examples |
| Mounted page contract confidence | No CLI change | Existing contract APIs | No wire change | Existing `FormContract` | Contract docs if wording changes | `forum_shell` | Forms, form routes, example coverage |
| Tenant/base-path URL RFC | No CLI change initially | Possible request-scoped URL helper | Full page, htmx, redirect, SSE URL semantics | TBD by RFC | Routing/deployment docs after implementation | Example after API settles | Routing/rendering tests after implementation |
| Production form ergonomics | `chirp check` guidance possible | Existing form/CSRF APIs first | htmx/non-htmx validation paths | Existing form dataclasses | Forms/security docs | Form examples | CSRF, forms, mounted page tests |
| Shell/OOB/SSE hardening | DevTools/check docs only | Existing return types/check APIs | OOB/SSE/replay guidance | Existing `ConnectionInfo`, `SSEEvent` | Htmx/devtools/realtime docs | Shell/realtime examples | Contract, browser, multi-client tests |
| Diagnostics and fixtures | Terminal output docs | Existing checker APIs | No protocol change | No type change | Contract category docs | Product-shaped fixtures | Docs and example tests |
| Component ecosystem | No core CLI change until scaffolds opt in | Optional `use_chirp_ui`/chirp-ui | htmx attrs generated by adapter | Typed component metadata blocked | Optional UI docs | ChirpUI examples | Boundary/filter/example tests |

## Not Now

- New return types.
- JSON/API side channels for product data.
- Client-side SPA or JavaScript build pipeline.
- Core dependency on chirp-ui.
- Product schemas, workflows, moderation, or forum implementation in Chirp.
- Shared-store client persistence before server-side cache semantics prove useful downstream.
- Contract severity promotions without maintainer review.
