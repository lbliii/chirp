---
title: Islands Contract (V1)
description: Framework-agnostic contract for isolated client-managed surfaces
draft: false
weight: 30
lang: en
type: doc
tags: [guides, islands, htmx, progressive-enhancement]
keywords: [islands, data-island, fragment_island, hydration, remount, fallback]
category: guide
---

## Islands are Chirp's no-build answer for client state

When a surface genuinely needs client-resident state, islands are the headlined
answer — **no VDOM, no build step, and zero per-client server view state.** That
last clause is the line: diff-push frameworks (LiveView, Hotwire) deliver
optimistic UI and rich client widgets by keeping a per-client copy of the view
*on the server*. Chirp does not. Islands own their DOM in the browser; the server
keeps returning authoritative HTML and remembers nothing about any one client.

Chirp ships **one blessed primitive that proves the model** — `optimistic_apply`
(below). It paints a mutation locally and instantly, lets htmx do the real
request, and reconciles by swapping the authoritative server fragment — all from
a snapshot that lives in the browser. The zero-server-view-state guarantee is
machine-checked, not asserted (`tests/test_islands.py`). Everything else is the
framework-agnostic mount contract you bring your own adapter to.

## Current State

Chirp ships a real V1 islands system. The following are implemented and available:

- **AppConfig flags** in `src/chirp/config.py`: `islands`, `islands_version`, `islands_contract_strict`
- **Runtime injection** in `src/chirp/app/compiler.py`: bootstrap script when `islands=True`
- **Islands bootstrap/runtime** in `src/chirp/server/islands.py`: mount/unmount lifecycle, htmx integration
- **Template helpers** in `src/chirp/templating/filters.py`: `island_props`, `island_attrs`
- **Static checks** in `src/chirp/contracts/rules_islands.py`: metadata validation
- **Test coverage** in `tests/test_islands.py` and `tests/test_contracts.py`

### Already Shipped

- V1 mount contract and helpers
- Inline runtime bootstrap
- Dynamic adapter loading via `data-island-src`
- Lifecycle events (`chirp:island:*`)
- Primitive metadata conventions and schema checks
- `app.check()` enforcement
- The blessed `optimistic_apply` primitive (first-party, client-only) and the
  `optimistic_attrs(...)` helper
- A prominent end-to-end example: `examples/standalone/optimistic_apply/`

### Not Yet Strong In-Repo

- First-party adapter modules for the *other* (convention-only) primitives
- Deep integration between islands and `PageComposition.regions`
- Env-based config loading for islands flags in `AppConfig.from_env()`

## Philosophy

Chirp islands are the framework's answer for genuinely client-managed surfaces.
Chirp remains HTML-over-the-wire by default: routing, shell composition,
fragments, OOB updates, and most mutations stay server-owned. Islands provide
an explicit, validated mount contract for the narrower class of widgets whose
state and DOM must live in the browser.

Islands are:

- explicit mount roots with stable metadata
- progressive enhancement over SSR fallback HTML
- compatible with no-build ES modules
- validated by `app.check()`
- deliberately separate from shell/navigation ownership

Islands are not:

- a replacement for `Page`, `Fragment`, `OOB`, or app-shell rendering
- a client router
- global hydration
- a rebranding of Chirp as a SPA framework

## Boundaries: `data-island` vs `fragment_island`

Two concepts look similar in prose but are different in code. The proposal must
clearly separate them.

### `data-island` Islands

These are the real islands runtime contract shipped by Chirp V1. They are
client-runtime islands: elements where a JavaScript adapter mounts and owns the
DOM.

Relevant files:

- `src/chirp/server/islands.py`
- `src/chirp/templating/filters.py`
- This guide

### `fragment_island` / `safe_region`

These are ChirpUI/HTMX safety primitives that isolate local mutation regions
from inherited `hx-*` behavior. They use `hx-disinherit` to prevent shell-level
`hx-target` / `hx-swap` from bleeding into form submissions and fragment swaps.

Relevant files:

- `src/chirp_ui/templates/chirpui/fragment_island.html`
- [App Shells](/chirp/docs/build-apps/ui-extensions/app-shell/)

**`fragment_island` is a swap-safety boundary, not the same thing as a
client-runtime island.** Use it when you need semantic grouping or when a
region needs its own `hx-target` / `hx-swap` defaults. It does not run any
client-side JavaScript or mount framework adapters.

## Architecture

Islands complement Chirp's existing rendering pipeline; they do not replace it.

### Server-Owned Pipeline Stays Primary

Chirp has a coherent composition model:

- semantic return types in `src/chirp/templating/returns.py`
- composition types in `src/chirp/templating/composition.py`
- request-aware planning in `src/chirp/templating/render_plan.py`
- negotiation in `src/chirp/server/negotiation.py`

### Ownership Model

Document three ownership classes:

- **Server-owned regions**: normal fragments, OOB targets, shell actions, SSE
  display blocks
- **Client-owned surfaces**: `data-island` roots and their internal DOM
- **Shared boundaries**: coarse remount/invalidation boundaries where server
  swaps may replace an island root but should not patch inside it

This ownership model is implied by [SSE Patterns](/chirp/docs/build-apps/streaming-updates/sse-patterns/):
client-managed surfaces should not be reactively re-rendered. Do not register
client-owned blocks in the reactive dependency index. See [App Shells](/chirp/docs/build-apps/ui-extensions/app-shell/)
for how islands fit inside shell layouts and OOB regions.

## Shell Constraints

ChirpUI shell contracts that islands must respect:

- `#main` is the persistent page-content swap target
- Shell OOB regions are stable server-owned containers:
  - `#chirpui-topbar-breadcrumbs`
  - `#chirpui-sidebar-nav`
  - `#chirpui-document-title`
  - `#chirp-shell-actions` or custom `ShellActions.target`
- `sidebar_link()` and `nav_link()` assume boosted navigation targets `#main`

Islands may live inside those regions, but they must not take ownership of the
OOB target containers themselves. Custom shells may not expose every built-in
OOB target id automatically.

## Mount Root Contract

An island mount root is any element with `data-island`:

```html
<div
  id="editor-root"
  data-island="editor"
  data-island-version="1"
  data-island-src="/static/editor.js"
  data-island-props="{&quot;doc_id&quot;:42,&quot;mode&quot;:&quot;advanced&quot;}"
>
  <p>Fallback editor UI for no-JS mode.</p>
</div>
```

Supported attributes:

- `data-island` (required): logical island name used by your client adapter.
- `data-island-version` (recommended): contract/runtime version (default `"1"`).
- `data-island-props` (optional): JSON payload for initial state.
- `data-island-src` (optional): adapter/runtime hint for lazy loaders (never use `javascript:`).
- `id` (recommended): stable mount id for deterministic remount targeting.
- `data-island-primitive` (optional): explicit primitive type tag for contract checks.

### Props Rules

- Props must be JSON-serializable (`dict`, `list`, string, number, boolean, null).
- Chirp helpers serialize and escape props for HTML attributes.
- Avoid hand-writing JSON in templates; use helpers:
  - `{{ state | island_props }}`
  - `{{ island_attrs("editor", props=state, mount_id="editor-root") }}`

## Lifecycle Events

With `AppConfig(islands=True)`, Chirp injects a small runtime that:

- scans for `[data-island]` on page load
- unmounts islands before htmx swaps
- mounts/remounts islands after htmx swaps

Browser events emitted:

- `chirp:island:mount`
- `chirp:island:unmount`
- `chirp:island:remount`
- `chirp:island:error`
- `chirp:islands:ready`
- `chirp:island:state` (state channel)
- `chirp:island:action` (action channel)

Each event `detail` includes:

- `name`, `id`, `version`, `src`, `props`, `element`

The blessed `optimistic_apply` primitive emits on the action channel:
`apply`/`optimistic` when it paints locally, `confirm`/`confirmed` when the
authoritative fragment swaps in, and `revert`/`reverted` when it rolls back.

## The blessed `optimistic_apply` primitive

`optimistic_apply` is the one primitive Chirp ships the runtime behavior for, so
mounting it Just Works with a contract guarantee — unlike the other primitives,
which are conventions you back with your own adapter. It paints a mutation
locally and instantly from the client's **own** pre-mutation snapshot, lets htmx
do the real request, swaps the authoritative server fragment on success
(last-write-wins), and reverts to the snapshot only when no authoritative
fragment lands.

Put the htmx trigger and `optimistic_attrs(...)` on the **same** element:

```html
<button
    id="like-btn"
    hx-post="/toggle-like"
    hx-target="#like-btn"
    hx-swap="outerHTML"
    {{ optimistic_attrs([
         {"op": "toggleClass", "value": "liked"},
         {"op": "setText", "expr": "+1", "sel": ".like-count"},
         {"op": "disable"},
       ], mount_id="like-btn") }}>
  <span class="like-count">{{ count }}</span> Like
</button>
```

```python
@app.route("/toggle-like", methods=["POST"])
def toggle_like():
    post = like(post_id)                                  # ordinary mutation
    return Fragment("post.html", "like_btn", post=post)   # authoritative fragment
```

See `examples/standalone/optimistic_apply/` for a runnable demo (a confirmed Like
and a reverting failure).

### Why this preserves the north star

**Chirp holds zero per-client server view state.** The rollback baseline is a
tab-local JavaScript snapshot — never a server-held copy. The handler is
byte-identical with or without the adapter; it is never told an optimistic apply
happened and allocates nothing per client/connection. Reconciliation is the
ordinary authoritative-fragment swap, not a server-held per-client merge. The
shipped runtime opens no transport of its own and persists nothing across the
client/server boundary — both halves are enforced by the
`TestOptimisticApplyGuardrail` gates.

### The op vocabulary

`ops` is a non-empty list of reversible operations. Each is applied forward on
arm and inverted on revert from the live DOM:

| op | keys | effect |
|----|------|--------|
| `addClass` / `removeClass` / `toggleClass` | `value`, optional `sel` | class mutation |
| `setText` | `value`, **or** `expr` (`"+1"`/`"-1"`), optional `sel` | text / numeric delta |
| `setAttr` | `name`, `value`, optional `sel` | set attribute |
| `removeAttr` | `name`, optional `sel` | remove attribute |
| `disable` | — | disable the trigger (blocks double-fire) |

`sel` scopes an op to a descendant of the region (default region = the mount
element). `optimistic_attrs(...)` rejects any unknown op or any
server-correlation key at render time, so the helper can never emit a mount that
would grow server view state.

There is deliberately **no `setHtml`/raw-HTML op** in v1: raw-HTML optimism is an
XSS surface and risks duplicate DOM on non-replacing swaps. Reach for a real
island when you need it.

### The ~80% ceiling (by design)

`optimistic_apply` closes ~80% of the optimistic-UI gap with zero server state.
What it does **not** do:

- **One in-flight optimistic mutation per region.** A re-trigger keeps the
  original pre-mutation snapshot, so revert always returns to the true baseline.
- **Last-write-wins** via the authoritative fragment swap. No operational
  transforms, no CRDTs, no concurrent-edit merge.
- **Requires a replacing swap** (`outerHTML`/`innerHTML` covering the region).
  Non-replacing swaps (`beforeend`/`afterend`/`append`) would leave both the
  optimistic node and the server node.
- **A `ValidationError(422)` that swaps an authoritative fragment is the truth**
  — the re-rendered form wins, no client revert. The snapshot is used only when
  *no* authoritative fragment lands (network/send error, timeout, non-swapping
  5xx).
- **Keep the region leaf, server-owned DOM.** Do not nest another island inside
  an `optimistic_apply` region; the coarse fallback revert would orphan it.

If you need collaborative concurrent editing with convergence, this is the wrong
tool — reach for a framework island with its own CRDT.

> **Cut line:** the feature is cut (deleted), not shipped thin, if it ever needs
> a request field correlating a client's optimistic apply with its response, a
> server-side map keyed by client/connection of in-flight mutations, or a
> server-held pre-mutation baseline. The `test_holds_zero_server_state` gate is
> the trip-wire.

## Runtime Configuration

```python
from chirp import App, AppConfig

app = App(
    AppConfig(
        islands=True,
        islands_version="1",
        islands_contract_strict=True,  # optional mount-id/version WARNINGs in app.check()
    )
)
```

Islands metadata **ERROR** checks (malformed props, unsafe `src`, invalid
version, required primitive keys, `optimistic_apply` op validation, and
server-correlation keys) run by default in `app.check()` regardless of
`islands_contract_strict` — that flag only adds advisory mount-id/version
warnings.

`app.check()` statically validates only **literal** `data-island-props` (it
cannot see the canonical `{{ optimistic_attrs(...) }}` helper form or any
`{{ }}`-bearing props, which it leaves untouched). For the helper form, the
same op vocabulary is enforced at **render time** by `optimistic_attrs(...)`
(which raises rather than emit an invalid or server-correlated mount) — that is
the authoritative guard. Both paths share one validator, so they cannot drift.

## Validation

`app.check()` / `chirp check` check islands metadata:

- malformed `data-island-props` JSON -> error
- invalid `data-island-version` format -> error
- unsafe `data-island-src` (`javascript:`) -> error
- optional strict mode warning when island roots omit `id`
- optional strict mode warning when templates omit `data-island-version`
- primitive schema checks for known no-build primitives

Known primitive contracts:

- `state_sync` -> `stateKey`
- `action_queue` -> `actionId`
- `draft_store` -> `draftKey`
- `grid_state` -> `stateKey`, `columns`
- `wizard_state` -> `stateKey`, `steps`
- `upload_state` -> `stateKey`, `endpoint`
- `optimistic_apply` -> `ops` (blessed; see above — also rejects unknown ops and
  server-correlation keys)

## Diagnostics

The runtime emits `chirp:island:error` for mount-level issues:

- malformed `data-island-props` (runtime parse failure)
- unsafe `data-island-src`
- mount/runtime version mismatch (warning-level event)

The runtime also exposes a small channel API:

- `window.chirpIslands.register(name, adapter)`
- `window.chirpIslands.emitState(payload, state)`
- `window.chirpIslands.emitAction(payload, action, status, extra)`
- `window.chirpIslands.channels` (`state`, `action`, `error`)

## Graceful Degradation

Always place useful fallback markup inside the mount root. If island runtime
fails, the SSR fallback remains visible and functional.

## Risks

- **Conflating HTMX-safe region boundaries with client-runtime islands** — use
  `fragment_island` for swap safety; use `data-island` for client-managed DOM.
- **Letting islands become a second default rendering model** — Chirp stays
  server-first; islands are an escape hatch.
- **Allowing server swaps to patch inside client-owned DOM** — establish
  explicit ownership; do not re-render client-managed surfaces via SSE or OOB.
- **Assuming all ChirpUI shells expose every built-in OOB target id** — custom
  shells may omit or rename targets; document your shell's contract.

## Roadmap

### V1.5: Positioning and Documentation Cleanup

- Clarify the distinction between `data-island` and `fragment_island`
- Add ownership-language docs for server-owned vs client-owned surfaces
- Connect islands guidance directly to app-shell and SSE docs
- Add one end-to-end no-build example using `island_attrs(...)` — see `examples/chirpui/islands_shell/`
- Islands + app shell: `examples/chirpui/islands_shell/`
- Islands + htmx fragment swap: `examples/chirpui/islands_shell/` (pages with client-managed state)

### V2: Render-Pipeline Alignment

- Explore how islands can participate more explicitly in `PageComposition` and
  `RegionUpdate`
- Define coarse invalidation/remount semantics around HTMX swaps
- Document how server-owned OOB regions can host remount-safe islands without
  excessive churn

### V3: Optional Higher-Level Ergonomics

- Stronger action/state conventions over the existing runtime channels
- Optional adapter packages or reference implementations
- Clearer realtime guidance for client-owned surfaces receiving JSON/operation
  streams rather than HTML patches

## Non-goals (V1)

- no built-in framework adapter (React/Svelte/Vue are user-land)
- no global hydration framework
- no client router replacement
