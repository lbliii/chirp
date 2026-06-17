---
title: Alpine.js
description: Local UI state with Alpine.js — dropdowns, modals, tabs — alongside htmx for server round-trips
draft: false
weight: 20
lang: en
type: doc
tags: [guides, alpine, htmx, client-state]
keywords: [alpine, dropdown, modal, tabs, local-state, csp]
category: guide
---

## What Alpine is for

[Alpine.js](https://alpinejs.dev) handles UI state that lives entirely in the
browser — open/closed dropdowns, modals, active tabs, accordions — the
interactions that don't need a server round-trip.

Reach for Alpine when a click should change what's on screen without fetching
anything. Reach for htmx when the click needs HTML from the server: a
[[docs/build-apps/html-fragments/fragments|fragment]] swap, a form submit, or an
[[docs/build-apps/streaming-updates/server-sent-events|SSE]] update.

| Use Alpine for | Use htmx for |
|----------------|--------------|
| Dropdowns, modals, tabs | Form submissions, partial swaps |
| Toggles, accordions | Search-as-you-type |
| Local validation before submit | SSE live updates |
| Client-only state | Server-driven content |

Chirp ships the Alpine wiring you turn on with one config flag. The Alpine
script is injected for you, and a small set of template macros (`dropdown`,
`modal`, `tabs`) give you accessible components out of the box.

## Enable it

Set `AppConfig(alpine=True)`:

```python
from chirp import App, AppConfig

config = AppConfig(alpine=True)
app = App(config=config)
```

That's the whole setup. Chirp injects the Alpine script (core plus plugins)
before `</body>` on every full-page HTML response, so your templates can use
Alpine attributes (`x-data`, `x-show`, `@click`) anywhere.

:::{note}
If you use [[docs/build-apps/ui-extensions/chirp-ui|chirp-ui]], `use_chirp_ui(app)`
turns Alpine on for you — its components require it — so you don't set the flag
yourself.

```python
from chirp import App, use_chirp_ui

app = App()
use_chirp_ui(app)  # sets alpine=True automatically
```
:::

See [[docs/about/core-concepts/configuration|AppConfig fields]] for the full
option list.

## Use the macros

Import Chirp's Alpine macros and call them in your templates:

```html
{% from "chirp/alpine.html" import dropdown, modal, tabs %}

{% call dropdown("Menu") %}
  <a href="/a">Link A</a>
  <a href="/b">Link B</a>
{% end %}

{% call modal("confirm-dialog", title="Confirm") %}
  <p>Are you sure?</p>
  <button @click="open = false">Yes</button>
  <button @click="open = false">Cancel</button>
{% end %}

{% call tabs(["Overview", "Details"], "Overview") %}
  <div x-show="active === 'Overview'">Overview content</div>
  <div x-show="active === 'Details'">Details content</div>
{% end %}
```

Each macro ships its own Alpine state and accessibility attributes:

| Macro | Signature | Notes |
|-------|-----------|-------|
| `dropdown` | `dropdown(trigger="Menu", wrapper_class="", panel_class="")` | Toggle panel with click-outside and Escape; sets `aria-expanded`, `aria-haspopup`, `role="menu"`. |
| `modal` | `modal(id="chirp-modal", title="", wrapper_class="", content_class="", managed=true)` | Dialog with Escape to close; sets `role="dialog"`, `aria-modal`, `aria-hidden`. |
| `tabs` | `tabs(tab_names, default=none, tab_list_class="", panel_class="")` | Tab list plus a panel slot; caller writes `x-show="active === 'TabName'"` per panel. |

`modal` defaults to `managed=true` (self-contained `open` state). Set
`managed=false` to share a parent's `open` variable so a sibling button controls
it. Add `[x-cloak]{display:none!important}` to your CSS so a modal stays hidden
until Alpine initializes.

## Use it with htmx

Alpine 3 watches the DOM with a mutation observer, so when htmx swaps in HTML
that contains Alpine attributes, Alpine initializes them automatically — no
extra wiring.

A dropdown inside an htmx-loaded fragment works the same as one on the initial
page:

```html
<div id="user-card" hx-get="/users/1" hx-trigger="load" hx-swap="innerHTML">
  Loading...
</div>
```

The server returns the fragment, and Alpine wires up the dropdown when it lands:

```html
{% from "chirp/alpine.html" import dropdown %}
{% call dropdown("Actions") %}
  <a href="/users/1/edit">Edit</a>
  <button hx-delete="/users/1" hx-target="#user-card">Delete</button>
{% end %}
```

For a guided, end-to-end build mixing both, follow the
[[docs/tutorials/alpine-htmx|Alpine + htmx tutorial]].

## Register your own components

When you register a named Alpine component with the standard `Alpine.data()`,
the `alpine:init` event fires only once, on initial page load. Under htmx
boosted navigation, a swapped-in script that relies on `alpine:init` never
re-registers — the component is dead after the first navigation.

Use `Alpine.safeData(name, factory)` instead. It is a drop-in replacement for
`Alpine.data()` that works on both initial loads and boosted navigations:

```html
<script>
Alpine.safeData("counter", () => ({
  count: 0,
  increment() { this.count++; },
}));
</script>

<div x-data="counter">
  <span x-text="count"></span>
  <button @click="increment">+</button>
</div>
```

:::{tip} Why not `Alpine.data()`?
On the first page load, `Alpine.data()` must be called during or before
`alpine:init`, but after Alpine loads. On later htmx navigations Alpine is
already initialized, so `Alpine.data()` runs immediately. `Alpine.safeData()`
handles both: it queues registrations until Alpine is ready, then becomes a
direct passthrough.
:::

### Pass server data to a component

When a component needs structured data from the server, emit it as a
`<script type="application/json">` tag and read it from JavaScript — quoting
JSON inside an HTML attribute is unsafe. When `alpine=True`, Chirp registers a
template global, `alpine_json_config`, so you don't hand-write the tag:

```kida
{{ alpine_json_config("game-config", game_config) }}
<div x-data="matchGame()">...</div>
<script>
var cfg = JSON.parse(document.getElementById("game-config").textContent);
Alpine.safeData("matchGame", function() {
  return { rows: cfg.rows, cols: cfg.cols };
});
</script>
```

The first argument is the `id`; the second is any JSON-serializable value (pass
`None` for JSON `null`). Non-serializable values fall back to `default=str`, the
same as Kida's `| tojson` filter. For small configs, `{{ config | tojson(attr=true) }}`
inside a double-quoted attribute works too; the script-tag pattern scales better
for large payloads.

## Content-Security-Policy

An `alpine=True` app runs under a strict **nonce-only** CSP out of the box — a
`script-src` without `'unsafe-inline'`. Chirp builds the single inline Alpine
bootstrap per request and stamps it with the live CSP nonce, so it survives the
policy. You do not need `alpine_csp=True` just to satisfy a nonce policy.

:::{danger} Don't pin a static CSP over a chirp-ui app
[[docs/build-apps/ui-extensions/chirp-ui|chirp-ui]] owns its CSP: `use_chirp_ui(app)`
wires the per-request nonce policy with everything the shell needs, so you write
**no CSP at all**.

Adding your own `SecurityHeadersMiddleware(content_security_policy=...)` overrides
the nonce header and **silently kills the shell** — collapse, dropdowns, theme
toggle, modals, command palette all die with no console error. The `chirpui_csp`
contract check fails loud at `app.check()` time (ERROR in production, WARNING in
staging, silent in development) when a chirp-ui app's effective CSP would break
Alpine.

Need the other security headers? Pass `content_security_policy=None` so
`SecurityHeadersMiddleware` emits the clickjacking, MIME, and referrer headers
without fighting the nonce CSP.
:::

For the dev-vs-prod severity rules behind the `csp_nonce` and `chirpui_csp`
checks, see [[docs/quality/contracts-debugging/categories|contract categories]];
for production CSP wiring, see [[docs/quality/deployment/auth-hardening|auth hardening]].

:::{dropdown} Standalone CSP setup (nonce-only / eval-forbidding)
For a standalone app (no chirp-ui) on a strict nonce-only CSP:

1. Enable a per-request nonce — `AppConfig(csp_nonce_enabled=True)` auto-wires
   `CSPNonceMiddleware`. This rebuilds every framework inline `<script>` per
   request and stamps it with the live nonce, so it survives a nonce-only
   policy. Without a nonce mechanism, a static inline-forbidding CSP blocks the
   scripts and `app.check()` flags it via the `csp_nonce` contract.
2. Keep `AppConfig(alpine=True)` — no `alpine_csp` needed for a nonce policy.
3. Allow the external Alpine script source (for example
   `https://cdn.jsdelivr.net`). The plugin and core tags are external `src=`
   scripts and need no nonce.

For an `eval`-**forbidding** policy, also set `AppConfig(alpine_csp=True)`. The
`@alpinejs/csp` build evaluates `x-data` expressions without `eval`/`Function`,
so you can keep `'unsafe-eval'` out of your `script-src`.
:::

:::{dropdown} How Alpine injection works
Chirp is the single authority for Alpine.js injection. `AlpineInject` appends the
script block before the first `</body>` on:

- **Buffered HTML responses** — full pages and eligible buffered bodies.
- **Streaming HTML** — `StreamingResponse` bodies (for example `Suspense`,
  `Stream`, `TemplateStream`) are rewritten chunk-by-chunk so Alpine appears in
  the final document without buffering the whole stream in memory. See
  [[docs/build-apps/streaming-updates/html-streaming|streaming HTML responses]].

Fragment responses (htmx partials) and other non-HTML responses pass through
unchanged. If Alpine is already present before `</body>` (detected via
`data-chirp="alpine"`), injection is skipped to prevent double-loading.

The injected block contains the Alpine core (jsDelivr CDN), the **Mask**,
**Intersect**, and **Focus** plugins, the `modals` and `trays` stores for
chirp-ui components, and the `Alpine.safeData()` helper. When `use_chirp_ui(app)`
is active, full-page HTML also includes the chirp-ui behavior runtime that
registers its named controllers (dropdown, copy, theme, dialog targets, shell
and sidebar behavior) through the same helper.
:::

:::{note} See also
- [[docs/tutorials/alpine-htmx|Alpine + htmx tutorial]] — a guided end-to-end build
- [[docs/build-apps/ui-extensions/chirp-ui|chirp-ui]] — prebuilt components and shell
- [[docs/quality/deployment/auth-hardening|Auth hardening]] — production CSP and headers
- [[docs/quality/contracts-debugging/categories|Contract categories]] — the `csp_nonce` and `chirpui_csp` checks
:::

:::{related}
:::
