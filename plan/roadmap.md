# Chirp Roadmap

**Status**: Active roadmap synthesis  
**Updated**: 2026-05-09  
**Source**: `plan/drafted/`, release-readiness notes, code/test audit, and affected steward guidance

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
| `rfc-shared-store.md` | Open | No `chirp.stores` or `cached_deferred` implementation exists |
| `rfc-component-collection.md` | Not now | Separate `chirp-ui` package scope; still blocked on mature typed component contracts |
| `epic-pbp-forum-mvp.md` | Open product proof | No production forum exists; `examples/chirpui/forum_shell` is a compact pattern, not the product |

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

### 3. Shared Store Phase 1: Server-Side Deferred Cache

**Why now**: This is the only open framework RFC that is small, unblocked, and
directly supports real product pages. Phase 1 can stay server-side and avoid
the client-store/SSE complexity in later phases.

**Scope**:
- Implement a minimal, lock-protected TTL cache for Suspense/deferred values.
- Prefer an explicit API such as `DeferredCache` or `cached_deferred()` only
  after confirming the public shape.
- Keep Alpine store and SSE broadcast out of Phase 1.

**Required proof**:
- Tests for cache hit, miss, expiry, concurrent access, exception behavior, and
  Suspense integration.
- `uv run pytest tests/test_suspense.py tests/test_concurrency -q` for shared
  state changes.
- `uv run ty check src/chirp/` if public typing is added.

**Collateral**: public API docs if exported, Suspense docs, changelog fragment,
and at least one example only if the API becomes user-facing.

### 4. Play-By-Post Forum Productization, Sprint 0-2

**Why now**: Chirp has enough framework surface to build the first real product
without patching core. The forum should be rebased from the compact
`examples/chirpui/forum_shell` pattern and current framework capabilities,
rather than implemented as a greenfield plan from the older draft.

**Scope**:
- Start with Sprint 0 capability refresh and product architecture: what
  `forum_shell` already proves, what needs persistence, and which behaviors
  belong in product code rather than Chirp.
- Sprint 1 auth flows: registration, login, logout, password reset, session
  hardening, and safe redirect behavior.
- Sprint 2 core boards/threads/posts with persistence, pagination, markdown,
  fragment paths, and validation.
- Use shipped `PageResult`, validation, auth/session, markdown, data, app
  shell, fragment/OOB, and reactive primitives.
- Treat any framework gap as an upstream issue or separate plan, not a hidden
  framework patch inside the product.

**Required proof**:
- Product tests for full page and htmx fragment paths.
- Contract checks passing for the forum app.
- Security review of registration/login/reset flows before any public deploy.
- Updated Sprint 0 capability matrix naming current shipped features and true
  product-only gaps.

**Collateral**: `docs/deployment/forum-production.md`,
`examples/chirpui/forum_shell/README.md`, example extraction candidates, and
upstream framework follow-ups discovered by product work.

### 5. Forum Realtime, Replay, And Presence Validation

**Why after MVP core**: Reactive Phase 2 is implemented, but it needs a real
consumer. The forum should prove audience filtering, presence, disconnect
callbacks, event identity, replay, and selective context are enough for
product-scale use.

**Scope**:
- Per-thread SSE streams.
- Event ids defined as replayable domain cursors, likely post ids per thread.
- `Last-Event-ID` replay behavior for missed posts after reconnect.
- Presence count and disconnect cleanup.
- Heartbeat/TTL semantics for stale connections and duplicate tabs.
- New-post and unread-count updates.
- Notification patterns only after thread posting works.

**Required proof**:
- Multi-client SSE tests.
- Integration test that sends `Last-Event-ID` and receives only missed post
  fragments while preserving notification/OOB behavior.
- Contract data for reactive emitted paths and connection-aware scopes.
- Browser smoke with two tabs, tab close, duplicate tabs, and reconnect.

**Collateral**: `examples/standalone/reactive_tasks` if patterns change,
realtime docs, deployment guidance for long-lived connections.

### 6. Component Collection And Component-Call Contracts

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
| Contracts | Finish proof/collateral for contract-heavy plans before adding new checks | `app.check()` must stay actionable, fast, and low-noise |
| Rendering | Close fragment/SSE example audit before changing Suspense again | The visible DOM contract is the user-facing risk |
| Realtime/server | Validate implemented reactive features in a real app | Per-event and disconnect boundaries need product pressure |
| Realtime/server | Define replay/event-id semantics before forum realtime | Users can miss posts after tab sleep or network blips without a replay contract |
| Data/security/pages | Put product work after framework surfaces are stable | Forum auth/data/page flows are higher risk than examples |
| Extensions/CLI/examples | Keep chirp-ui/component work optional and documented | Avoid making optional UI packages part of Chirp core |
| Benchmarks | Require evidence for hot-path or sync-path changes | Roadmap items here are mostly not performance-sensitive yet |

Deferred findings:
- Shared-store Phase 2 Alpine persistence and Phase 3 SSE broadcast are deferred
  until Phase 1 has real use.
- Full PBP moderation, full-text search, rich editor, uploads, and theming are
  outside the first product proof.
- Component collection and component-call validation wait for typed component
  metadata.
- `app.check()` large-template timing proof is tracked under contract docs
  parity, but does not block product work unless startup checks regress.

Minority reports:
- A product-first path could start the forum before shared-store Phase 1. That
  is viable if the first forum milestone avoids cross-page deferred data.
- A stricter cleanup path could move all implemented plans out of
  `plan/drafted/` immediately. This roadmap keeps status-note cleanup first so
  link drift can be checked before file moves.

## Parity Matrix

| Contract | API/CLI | Programmatic | Protocol | Schema/Types | Docs | Examples | Tests |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Planning hygiene | No CLI change | No runtime change | No protocol change | No type change | Update `plan/` index and statuses | No example change | Link drift if moving files |
| Fragment/SSE audit | No CLI change | Existing return types only | SSE `message` and fragment-block behavior | No new types | Streaming and fragment docs may need wording | Gallery/SSE/reactive examples | Contract, templating, browser smoke |
| Contract/reactive docs parity | `chirp check` docs only | Existing check/reactive APIs | No protocol change | No type change | Category and reactive guides | Reactive/forum examples | Docs, contracts, examples |
| Shared store Phase 1 | Possible public export TBD | New deferred-cache helper | No wire change | Frozen/slotted cache/result types if public | Suspense/cache docs | Optional example after API settles | Suspense, concurrency, typing |
| PBP forum MVP | No framework CLI change initially | Product app only | htmx, fragments, OOB, SSE later | Product schema/migrations | Product deployment notes | Extract patterns later | Product TestClient and contract checks |
| Realtime forum validation | No CLI change | Existing reactive API | EventStream/SSE per-thread behavior, replay ids | Existing `ConnectionInfo`, `ChangeEvent` | Realtime/deployment docs | `reactive_tasks` if pattern changes | Multi-client/reconnect SSE tests |
| Component ecosystem | No core CLI change until scaffolds opt in | Optional `use_chirp_ui`/chirp-ui | htmx attrs generated by adapter | Typed component metadata blocked | Optional UI docs | ChirpUI examples | Boundary/filter/example tests |

## Not Now

- New return types.
- JSON/API side channels for forum data.
- Client-side SPA or JavaScript build pipeline.
- Core dependency on chirp-ui.
- Shared-store client persistence before server-side cache semantics are proven.
- Contract severity promotions without maintainer review.
