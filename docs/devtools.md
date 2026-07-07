# Chirp DevTools

Chirp DevTools is the debug-mode browser overlay for htmx and hypermedia
behavior. It is intentionally opt-in: enable it while developing, and keep it
off in production.

DevTools is native Chirp runtime wiring. Debug assets, browser reload, internal
debug endpoints, and framework-owned routes are published during app freeze as
internal wiring and validated by `app.check()`. Browser code listens to public
htmx lifecycle events, but Chirp-owned facts such as render intent, render-plan
metadata, and EventStream lifecycle traces come from the server.

DevTools accepts both htmx 2's camel-case lifecycle events and htmx 4's
colon-separated fetch-era events. It correlates htmx 2 through the XHR and
htmx 4 through `detail.ctx` / `detail.ctx.request`. When the
`htmx-2-compat` extension emits both names for one action, the shared request
context suppresses duplicate request, history, OOB, and error records.

## Enable It

Use the development CLI when possible:

```bash
chirp dev app:app
```

That command forces `debug=True` for the running app. Without the CLI, configure
the app directly:

```python
from chirp import App, AppConfig

app = App(AppConfig(debug=True))
```

If an app uses `AppConfig.from_env()`, `CHIRP_DEBUG=1` enables debug mode.

## Use It

Open the app in a browser:

- `Ctrl+Shift+D` toggles the DevTools drawer.
- `Ctrl+Shift+K` toggles the inspector for effective `hx-*` settings.
- Expanded htmx request rows include Swap Doctor diagnostics for broad
  inherited targets, missing `hx-select` matches, no-op swaps, full-page
  documents returned to fragments, missing targets, and render-plan clues.

The SSE tab shows native Chirp `EventStream` traces. It does not replace
`window.EventSource`. Framework streams such as browser reload are hidden by
default so application streams stay readable.

## Debug Contract

In debug mode, Chirp reserves its internal URL space, including:

- `/__chirp/debug/htmx.js`
- `/__chirp/debug/highlight`
- `/__chirp/debug/fragment-targets`
- `/__chirp/debug/manifest.json`
- `/__chirp/debug/traces.json`
- `/__chirp/routes`
- `/__chirp__/dev-reload`
- `/_frag/...`

Registering an application route in that space fails during freeze. This keeps
debug behavior consistent during local navigation instead of letting framework
diagnostics shadow user routes.

`/__chirp/debug/manifest.json` exposes the internal wiring manifest to DevTools.
`/__chirp/debug/traces.json` exposes bounded debug trace records; by default it
omits internal framework traffic, and `?internal=1` includes it for framework
debugging.

## Agent Workflow

Browser-capable agents should activate debug mode when investigating htmx,
OOB, Suspense, SSE, fragment-target, or content-negotiation bugs. After opening
the app, evaluate these commands in the browser context:

```javascript
window.ChirpHtmxDebug.help()
window.ChirpHtmxDebug.exportRecordsJson()
```

`help()` describes the available API. `exportRecordsJson()` returns htmx
requests, errors, SSE connections and events, View Transition events, render
plans, and Swap Doctor records in a machine-readable form.

For application lifecycle hooks during the transition, register both event
names and deduplicate by request context:

```javascript
function onHtmxLifecycle(names, handler) {
  const seen = new WeakSet();
  for (const name of names) {
    document.addEventListener(name, (event) => {
      const token = event.detail?.ctx || event.detail;
      if (token && seen.has(token)) return;
      if (token) seen.add(token);
      handler(event);
    });
  }
}

onHtmxLifecycle(["htmx:afterSwap", "htmx:after:swap"], (event) => {
  const detail = event.detail || {};
  const target = detail.ctx?.target || detail.target;
  initializeWidgets(target);
});
```

Use `htmx.onLoad(callback)` for process hooks when possible. The public helper
maps to htmx 2's load lifecycle and htmx 4's `htmx:after:process` event.

## Export Shape

`window.ChirpHtmxDebug.exportRecordsJson()` returns JSON with these top-level
fields:

- `records`: htmx request records with request/response headers, render intent,
  typed return traces, render-plan data, effective `hx-*`, Swap Doctor evidence,
  and body previews.
- `errors`: htmx and DevTools warnings/errors.
- `historyEvents`: deduplicated push, replace, update, and restore events.
- `sseConnections`: native Chirp EventStream connection summaries.
- `sseEvents`: native Chirp EventStream lifecycle and event trace records.
- `vtEvents`: View Transition lifecycle records.

`X-Chirp-Return-Trace` is a compact debug header that records the typed return
branch Chirp negotiated, such as `Template`, `Fragment`, `PageComposition`,
`OOB`, `Suspense`, `Stream`, `EventStream`, `Action`, or `ValidationError`.
It is diagnostic metadata only; it does not change response negotiation.
