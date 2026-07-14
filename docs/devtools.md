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
- Request rows use htmx's reported verb, show whether the method is safe or
  mutating, and preserve response timing and error-body evidence. RFC 10008
  `QUERY` is classified as safe even when issued programmatically with
  `htmx.ajax("QUERY", ...)`.

The SSE tab shows native Chirp `EventStream` traces. It does not replace
`window.EventSource`. Framework streams such as browser reload are hidden by
default so application streams stay readable.

The Reload tab shows the debug template-reload planner's redacted decision for
each changed HTML template: logical template name, changed/added/removed named
blocks, `patch`/`diagnose`/`reload` outcome, reason, target when known, and
monotonic revision. The records survive the ensuing full-page reload in
tab-scoped session storage. This phase is observational: the existing browser
reload still happens, and a `patch` decision does not mutate the DOM.

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
window.ChirpHtmxDebug.transitionCoverage(["normal", "boosted", "targeted"])
```

`help()` describes the available API. `exportRecordsJson()` returns htmx
requests, errors, SSE connections and events, View Transition events, render
plans, template-reload decisions, compiled-transition evidence, and Swap Doctor records in a
machine-readable form. `transitionCoverage()` compares the modes you explicitly
expect with the bounded observations captured by the server. It reports gaps;
it does not claim that a static route graph proves browser behavior.

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
  method semantics, timing phases, response content type, and body previews.
- `errors`: htmx and DevTools warnings/errors.
- `historyEvents`: deduplicated push, replace, update, and restore events.
- `sseConnections`: native Chirp EventStream connection summaries.
- `sseEvents`: native Chirp EventStream lifecycle and event trace records.
- `transitionTraces`: bounded server observations that correlate a route and
  request mode with opaque compiled transition IDs and public-safe
  descriptions.
- `transitionCoverage`: the observed mode, observation-ID, and compiled-ID
  summary at export time.
- `vtEvents`: View Transition lifecycle records.
- `templateReloadPlans`: bounded, redacted template planner records. These
  contain logical template/block/target identities and diagnostic type/line,
  but no source filename, rendered HTML, request context, or credentials.

`X-Chirp-Return-Trace` is a compact debug header that records the typed return
branch Chirp negotiated, such as `Template`, `Fragment`, `PageComposition`,
`OOB`, `Suspense`, `Stream`, `EventStream`, `Action`, or `ValidationError`.
When the response comes through the frozen app runtime, the trace also carries
the route's compiled ID, a stable observation ID, request-mode tags, and the
relevant compiled transition IDs/descriptions. Dynamic path values and context
values are not included. The header is diagnostic metadata only; it does not
change response negotiation. It also records the request method and request
content type so a QUERY trace can be distinguished from the same render branch
reached by GET or a mutation.

## Test Evidence

Use the testing helpers with responses from a debug app when a contract test
needs to name intentionally untested request modes:

```python
from chirp.testing import transition_coverage

report = transition_coverage(
    responses,
    expected_modes=("normal", "boosted", "targeted"),
)
assert report.untested_modes == ()
```

`transition_coverage()` can also compare explicit compiled transition IDs. It
only reports evidence from real `TestClient` responses; DOM swap and history
behavior still require the browser lane.
