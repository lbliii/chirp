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

When an htmx swap paints the wrong thing — a whole page inside a `<div>`, a
section that goes blank, an out-of-band update that does nothing, a
[[docs/build-apps/streaming-updates/html-streaming|Suspense]] skeleton that never
resolves — work through this page top to bottom: run the contract checker, turn
on debug mode, then read the symptom table. Most swap bugs trace to one wrong
[[docs/about/core-concepts/return-values|return type]].

## Diagnose in order

::::{steps}
:::{step} Start with the contract

Before guessing from screenshots, run the contract checker:

```bash
chirp check app:app
```

For CI or release branches, fail the build on warnings too:

```bash
chirp check app:app --warnings-as-errors
```

`chirp check` catches the failures that most often turn into blank or wrong DOM:
missing template blocks, route-name collisions, OOB registrations that no layout
satisfies, route-directory metadata mismatches, reactive block typos,
form-contract gaps, and known htmx footguns. For the full list of categories and
their severities, see [[docs/quality/contracts-debugging/categories|contract categories]].
:::{/step}

:::{step} Enable debug mode

Use the development CLI when possible:

```bash
chirp dev app:app
```

Or configure the app directly:

```python
from chirp import App, AppConfig

app = App(AppConfig(debug=True))
```

Debug mode enables richer errors, template reloads, debug headers, the fragment
validator (`debug_fragment_validator`, on by default), and the browser DevTools
overlay.
:::{/step}

:::{step} Open browser DevTools

Open the app and press `Ctrl+Shift+D` to open Chirp DevTools.

For browser-capable agents, export records straight from the page:

```javascript
window.ChirpHtmxDebug.help()
window.ChirpHtmxDebug.exportRecordsJson()
```

The exported records include htmx requests, errors, SSE connections and events,
View Transition events, render plans, and Swap Doctor diagnostics. Reach for this
when the visual symptom is vague but the request, target, and render intent
should be precise.
:::{/step}
::::{/steps}

## Symptom table

| Symptom | Likely cause | First check |
| --- | --- | --- |
| A whole page appears inside a `<div>` | Handler returned `Template(...)` for an htmx request | Use `Page(...)` or `Fragment(...)`; the debug fragment validator should warn |
| A section goes blank after a swap | Targeted block is missing or rendered empty | `chirp check`; verify the `Fragment` or `Page` block name |
| OOB update does nothing | `hx-swap-oob` target id does not exist in the current layout | Check the OOB registry and layout block ids |
| Suspense skeleton never resolves | Deferred block was not discovered or mapped to the wrong target | Check `defer_blocks`, `defer_map`, and block dependencies |
| Empty list looks like loading | Template used `{% if items %}` for a deferred value | Use `{% if items is deferred %}` before testing resolved values |
| SSE stream stops after one bad event | Error boundary widened beyond one event | Check the `EventStream` generator and fragment render errors |
| SSE events arrive but DOM never updates | `sse-swap` event name mismatch or swap on the connect element | Run `chirp check` for `sse_crossref` / `sse_self_swap`; use `assert_sse_wired` in tests; put `sse-swap` on a child sink |
| Boosted link reloads the page | Link crosses shell boundaries or boost is disabled | Check `HX-Redirect`, shell layout domains, and `hx-boost` inheritance |
| Duplicate shell actions or badges appear | OOB region rendered inline and out-of-band | Register the region and keep the DOM id in one owner |

:::{warning}
The two highest-frequency swap bugs are both return-type or template mistakes:

- **A whole page renders inside a `<div>`** means the handler returned
  `Template(...)` for an htmx request. Return `Page(...)` (full page for
  browsers, fragment for htmx) or `Fragment(...)` instead.
- **An empty list shows the loading skeleton forever** means the template tested
  `{% if items %}` for a deferred value. An empty `list`, `tuple`, `""`, or `0`
  is falsy after resolution, so it reads as "still loading." Test
  `{% if items is deferred %}` for loading-vs-loaded — see
  [[docs/build-apps/streaming-updates/html-streaming|HTML streaming]].
:::

## Keep the return type honest

Most swap bugs reduce to the wrong return type:

| Need | Return |
| --- | --- |
| Full page only | `Template(...)` |
| Full page for browsers, fragment for htmx | `Page(...)` |
| One named block | `Fragment(...)` |
| Main fragment plus extra regions | `OOB(...)` |
| Initial shell plus deferred blocks | `Suspense(...)` |
| Post-load long-lived updates | `EventStream(...)` |

If the response shape is unclear, start at [[docs/about/core-concepts/return-values|Return Values]].

:::{dropdown} Advanced: debug headers
When `debug=True`, Chirp exposes request and route context through response
headers:

- `X-Chirp-Route-Kind`
- `X-Chirp-Route-Files`
- `X-Chirp-Route-Meta`
- `X-Chirp-Route-Section`
- `X-Chirp-Context-Chain`
- `X-Chirp-Shell-Context`

Inspect these when a filesystem route, section, shell mode, or layout chain does
not match the route you thought was serving the request.
:::{/dropdown}

:::{dropdown} Advanced: template-context contracts
Kida-powered template diagnostics report under their own categories:

| Category | Meaning | Typical fix |
| --- | --- | --- |
| `component` | A local `{% def %}` call has unknown, missing, duplicate, or literal type-mismatched arguments | Fix the call site or the component signature |
| `template_context` | An opt-in dotted context contract does not cover what the template reads | Add the missing path to `provided`, move it to `optional`, or stop reading it |
| `template_escape` | A template deliberately trusts markup, such as `\| safe`, and should document the trust boundary | Add `safe(reason="...")` or remove the trust override |
| `template_privacy` | A template reads sensitive-looking data such as tokens, secrets, or password paths | Confirm the value belongs in rendered output or remove it |

For dotted context checks, register template contracts through the contract
check-data channel:

```python
app.set_contract_check_data(
    "template_context_contracts",
    {
        "page.html": {
            "provided": {"page.title", "user.name"},
            "optional": {"flash.message"},
        }
    },
)
```
:::{/dropdown}

:::{note} See also
- [[docs/quality/contracts-debugging/categories|Contract Categories]]
- [[docs/quality/contracts-debugging/route-contract|Route Directory Contract]]
- [[docs/quality/contracts-debugging/oob-registry|OOB Registry]]
- [[docs/build-apps/ui-extensions/boosted-navigation|Boosted Navigation]]
- [[docs/build-apps/streaming-updates/html-streaming|Streaming HTML]]
- [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]]
:::
