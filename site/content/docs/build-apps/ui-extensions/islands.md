---
title: Islands
description: Mount client-owned JavaScript surfaces with no VDOM, no build step, and zero per-client server state.
draft: false
weight: 30
lang: en
type: doc
tags: [guides, islands, htmx, progressive-enhancement]
keywords: [islands, data-island, optimistic_apply, fragment_island, hydration, remount, fallback]
category: guide
---

## What islands are

An island is an explicit escape hatch for the rare surface that genuinely needs
client-resident state — a rich text editor, a drag-to-reorder list, a toggle that
must paint before the server answers. A `data-island` element marks where your
JavaScript adapter mounts and owns the DOM. There is no VDOM, no build step, and
**zero per-client server view state**: the server keeps returning authoritative
HTML and remembers nothing about any one client.

For the most common case — paint a mutation instantly, let htmx do the real
request, reconcile by swapping the server's answer — Chirp ships one blessed
primitive that works out of the box: `optimistic_apply`. Most readers need only
that. Everything else is a framework-agnostic mount contract you bring your own
adapter to.

:::{since} 0.8
:::

Islands are deliberately rare. Chirp stays server-first by default — routing,
shell composition, [[docs/build-apps/html-fragments/fragments|fragments and OOB updates]],
and most mutations stay server-owned.

:::{note}
Reach for an island only when fragments and OOB genuinely cannot express the
interaction. If a server round trip can paint the result, keep it server-owned.
:::

## When to reach for an island

Pick the lightest tool that expresses the interaction. An island is the heaviest
option here, so most of the time you want one of the others.

:::{list-table}
:header-rows: 1

* - You need
  - Reach for
* - Client-owned DOM (editor, drag-reorder, a widget that manages itself)
  - A `data-island` island
* - Instant feedback on a mutation, reconciled by the server's answer
  - `optimistic_apply` (a blessed island primitive — see below)
* - A region with its own `hx-target` / `hx-swap` defaults and swap safety
  - `fragment_island` ([[docs/build-apps/ui-extensions/app-shell|app shells and OOB regions]]) — **not** an island
* - Realtime push after the page loads
  - [[docs/build-apps/streaming-updates/sse-patterns|EventStream / SSE]]
:::

`fragment_island` looks similar in prose but is a different thing in code: it is
an HTMX swap-safety boundary that isolates a region from inherited `hx-*`
behavior. It runs no client-side JavaScript and mounts no adapter. Use it for
swap safety; use a `data-island` island for client-managed DOM.

## Minimal working example: `optimistic_apply`

`optimistic_apply` is the one primitive Chirp ships the runtime for, so it works
with a contract guarantee out of the box. It paints a mutation locally from the
client's **own** pre-mutation snapshot, lets htmx do the real request, swaps in
the authoritative server fragment on success (last-write-wins), and reverts to
the snapshot only when no authoritative fragment lands.

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

The handler is an ordinary mutation that returns the authoritative fragment. It
is never told an optimistic apply happened — [[docs/about/core-concepts/return-values|the return type is the intent]],
nothing more:

```python
@app.route("/")
def index():
    return Template("index.html", **_like_context())


@app.route("/toggle-like", methods=["POST"])
def toggle_like():
    """Ordinary mutation. Returns ONLY the authoritative fragment; the optimistic
    paint is confirmed when htmx swaps it in."""
    STATE["liked"] = not STATE["liked"]
    STATE["count"] += 1 if STATE["liked"] else -1
    return Fragment("index.html", "like_button", **_like_context())
```

*Source: [`examples/standalone/optimistic_apply/app.py`](https://github.com/lbliii/chirp/blob/main/examples/standalone/optimistic_apply/app.py).*

That is the whole loop. The button paints instantly; htmx posts; the
`like_button` fragment swaps in and confirms the paint. The full runnable demo
(a confirmed Like and a reverting failure) lives in
`examples/standalone/optimistic_apply/`.

## Common patterns

### Mount a custom island

Any element with `data-island` is a mount root. Use `island_attrs(...)` rather
than hand-writing the JSON attributes:

```html
<div{{ island_attrs("editor", props=state, mount_id="editor-root",
                    src="/static/editor.js") }}>
  <p>Fallback editor UI for no-JS mode.</p>
</div>
```

That renders the mount-root attributes your adapter reads:

:::{list-table}
:header-rows: 1

* - Attribute
  - Role
* - `data-island` (required)
  - Logical island name your client adapter registers against.
* - `data-island-version`
  - Contract/runtime version (default `"1"`).
* - `data-island-props`
  - JSON payload for initial state. Must be JSON-serializable.
* - `data-island-src`
  - Adapter/runtime hint for lazy loaders. Never `javascript:`.
* - `id`
  - Stable mount id for deterministic remount targeting.
:::

### Always ship fallback markup

Place useful markup *inside* the mount root. If the island runtime fails to load
or mount, the server-rendered fallback stays visible and functional. That
fallback is the no-JS experience.

### Turn the runtime on

```python
from chirp import App, AppConfig

app = App(
    AppConfig(
        islands=True,
        islands_version="1",
    )
)
```

With `islands=True`, Chirp injects a small runtime that scans for `[data-island]`
on load, unmounts islands before htmx swaps, and mounts or remounts them after.

## Gotchas

:::{warning}
**`optimistic_apply` needs a replacing swap, and islands never overlap
server-managed DOM.**

- Use a replacing `hx-swap` (`outerHTML` or `innerHTML` covering the region).
  Non-replacing swaps (`beforeend` / `afterend` / `append`) leave both the
  optimistic node and the server node — duplicate DOM.
- Never patch *inside* a client-owned island via SSE or OOB, and never nest an
  island inside an `optimistic_apply` region. The server may replace an island
  root wholesale, but it must not reach inside one. See
  [[docs/build-apps/streaming-updates/reactive-system|reactive re-render (don't re-render client-owned DOM)]].
:::

## Next step

Copy the runnable `optimistic_apply` demo — a confirmed Like and a reverting
failure — from `examples/standalone/optimistic_apply/`, wire it onto your own
mutation, then read [[docs/build-apps/streaming-updates/reactive-system|the reactive system]]
to keep server-managed regions from re-rendering over client-owned DOM.

## Advanced

::::{dropdown} The op vocabulary (and why there is no setHtml)
:icon: list

`ops` is a non-empty list of reversible operations. Each is applied forward when
the button fires and inverted on revert, read from the live DOM:

| op | keys | effect |
|----|------|--------|
| `addClass` / `removeClass` / `toggleClass` | `value`, optional `sel` | class mutation |
| `setText` | `value`, **or** `expr` (`"+1"` / `"-1"`), optional `sel` | text / numeric delta |
| `setAttr` | `name`, `value`, optional `sel` | set attribute |
| `removeAttr` | `name`, optional `sel` | remove attribute |
| `disable` | — | disable the trigger (blocks double-fire) |

`sel` scopes an op to a descendant of the region (the region defaults to the
mount element). `optimistic_attrs(...)` rejects any unknown op — or any
server-correlation key — at render time, raising rather than emitting a mount
that could grow server view state.

There is deliberately **no `setHtml` / raw-HTML op**: raw-HTML optimism is an XSS
surface and risks duplicate DOM on non-replacing swaps. When you need it, mount a
real custom island instead.
::::{/dropdown}

::::{dropdown} What optimistic_apply does not do (the ~80% ceiling)
:icon: info

`optimistic_apply` closes roughly the common 80% of optimistic-UI cases with
zero server state. The boundaries:

- **One in-flight optimistic mutation per region.** A re-trigger keeps the
  original pre-mutation snapshot, so revert always returns to the true baseline.
- **Last-write-wins** via the authoritative fragment swap. No operational
  transforms, no CRDTs, no concurrent-edit merge.
- **A `ValidationError(422)` that swaps a fragment is the truth.** The
  re-rendered form wins, with no client revert. The snapshot is used only when
  *no* authoritative fragment lands (network error, timeout, non-swapping 5xx).
- **The region stays leaf, server-owned DOM.** Do not nest another island inside
  it; the coarse fallback revert would orphan it.

If you need collaborative concurrent editing with convergence, this is the wrong
tool — reach for a custom island with its own CRDT.

**Zero per-client server state is guaranteed, not asserted.** The rollback
baseline is a tab-local JavaScript snapshot, never a server-held copy. The
handler is byte-identical with or without the adapter and allocates nothing per
client. The runtime opens no transport of its own and persists nothing across
the client/server boundary. A build guardrail enforces both halves — it fails
the build if a server-held optimistic store or a per-client branch ever appears.
::::{/dropdown}

::::{dropdown} Channel API & diagnostics
:icon: code

With `islands=True`, the runtime exposes a small channel API on `window`:

```js
window.chirpIslands.register(name, adapter);
window.chirpIslands.emitState(payload, state);
window.chirpIslands.emitAction(payload, action, status, extra);
window.chirpIslands.channels; // { state, action, error }
```

It emits browser events you can listen for: `chirp:island:mount`,
`chirp:island:unmount`, `chirp:island:remount`, `chirp:island:error`,
`chirp:islands:ready`, plus `chirp:island:state` and `chirp:island:action`.
Each event `detail` carries `name`, `id`, `version`, `src`, `props`, and
`element`.

`optimistic_apply` emits on the action channel: `apply`/`optimistic` when it
paints locally, `confirm`/`confirmed` when the authoritative fragment swaps in,
and `revert`/`reverted` when it rolls back. `chirp:island:error` fires for
malformed `data-island-props`, an unsafe `data-island-src`, or a mount/runtime
version mismatch.
::::{/dropdown}

::::{dropdown} Validation & strict mode
:icon: shield

Islands metadata is [[docs/quality/contracts-debugging/categories|validated at startup by app.check()]].
These are **ERROR** checks regardless of any flag:

- malformed `data-island-props` JSON
- invalid `data-island-version` format
- unsafe `data-island-src` (`javascript:`)
- `optimistic_apply` op validation and rejected server-correlation keys

`islands_contract_strict=True` adds advisory **WARNING** checks: island roots
that omit `id`, and templates that omit `data-island-version`.

`app.check()` can statically validate only **literal** `data-island-props`; it
leaves any `{{ }}`-bearing props (including the canonical `optimistic_attrs(...)`
form) untouched. For the helper form, `optimistic_attrs(...)` enforces the same
op vocabulary at render time and raises on an invalid or server-correlated
mount. Both paths share one validator, so they cannot drift.
::::{/dropdown}

:::{note} See also
- [[docs/build-apps/ui-extensions/app-shell|App shells and OOB regions]] — where islands fit inside shell layouts
- [[docs/build-apps/streaming-updates/reactive-system|Reactive system]] — why client-owned DOM must not be re-rendered
- [[docs/about/core-concepts/return-values|Return values]] — the return-type-is-intent model the handler relies on
:::
