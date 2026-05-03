---
title: Debugging Swaps
description: Use chirp check, debug headers, and DevTools to diagnose broken htmx, OOB, Suspense, and SSE updates
draft: false
weight: 12
lang: en
type: doc
tags: [debugging, htmx, contracts, devtools]
keywords: [debugging, swaps, chirp check, devtools, oob, suspense, sse]
category: guide
---

## Start With The Contract

When a page or fragment swaps incorrectly, run the contract checker before
guessing from screenshots:

```bash
chirp check app:app
```

For CI or release branches:

```bash
chirp check app:app --warnings-as-errors
```

`chirp check` catches the failures that most often turn into blank or wrong DOM:
missing template blocks, route-name collisions, OOB registrations that no
layout satisfies, route-directory metadata mismatches, reactive block typos,
form-contract gaps, and known htmx footguns.

## Then Enable Debug Mode

Use the development CLI when possible:

```bash
chirp dev app:app
```

Or configure the app directly:

```python
from chirp import App, AppConfig

app = App(AppConfig(debug=True))
```

Debug mode enables richer errors, template reloads, debug headers, fragment
validator warnings, and the browser DevTools overlay.

## Use Browser DevTools

Open the app and press `Ctrl+Shift+D` to open Chirp DevTools.

For browser-capable agents, export records from the page:

```javascript
window.ChirpHtmxDebug.help()
window.ChirpHtmxDebug.exportRecordsJson()
```

The exported records include htmx requests, errors, SSE connections and events,
View Transition events, render plans, and Swap Doctor diagnostics. Use this when
the visual symptom is vague but the request/target/render intent should be
precise.

## Symptom Table

| Symptom | Likely cause | First check |
| --- | --- | --- |
| A whole page appears inside a `<div>` | Handler returned `Template(...)` for an htmx request | Use `Page(...)` or `Fragment(...)`; debug fragment validator should warn |
| A section goes blank after a swap | Targeted block is missing or rendered empty | `chirp check`; verify the `Fragment` or `Page` block name |
| OOB update does nothing | `hx-swap-oob` target id does not exist in the current layout | Check the OOB registry and layout block ids |
| Suspense skeleton never resolves | Deferred block was not discovered or mapped to the wrong target | Check `defer_blocks`, `defer_map`, and block dependencies |
| Empty list looks like loading | Template used `{% if items %}` for a deferred value | Use `{% if items is not none %}` or `__chirp_defer_pending__` |
| SSE stream stops after one bad event | Error boundary widened beyond one event | Check `EventStream` generator and fragment render errors |
| Boosted link reloads the page | Link crosses shell boundaries or boost is disabled | Check `HX-Redirect`, shell layout domains, and `hx-boost` inheritance |
| Duplicate shell actions or badges appear | OOB region rendered inline and out-of-band | Register the region and keep the DOM id in one owner |

## Read The Headers

When `debug=True`, Chirp can expose request and route context through headers:

- `X-Chirp-Route-Kind`
- `X-Chirp-Route-Files`
- `X-Chirp-Route-Meta`
- `X-Chirp-Route-Section`
- `X-Chirp-Context-Chain`
- `X-Chirp-Shell-Context`

These are useful when a filesystem route, section, shell mode, or layout chain
does not match the route you thought was serving the request.

## Keep The Return Type Honest

Most swap bugs reduce to the wrong return type:

| Need | Return |
| --- | --- |
| Full page only | `Template(...)` |
| Full page for browsers, fragment for htmx | `Page(...)` |
| One named block | `Fragment(...)` |
| Main fragment plus extra regions | `OOB(...)` |
| Initial shell plus deferred blocks | `Suspense(...)` |
| Post-load long-lived updates | `EventStream(...)` |

If the response shape is unclear, start at [[docs/about/return-values|Return Values]].

## Related

- [[docs/quality/contracts-debugging/route-contract|Route Directory Contract]]
- [[docs/quality/contracts-debugging/oob-registry|OOB Registry]]
- [[docs/build-apps/ui-extensions/boosted-navigation|Boosted Navigation]]
- [[docs/build-apps/streaming-updates/html-streaming|Streaming HTML]]
- [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]]
