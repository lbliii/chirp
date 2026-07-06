---
title: htmx 4 Preview
description: Opt into Chirp's exact htmx 4 preview bundle, validate self-hosted assets, and roll back safely
draft: false
weight: 39
lang: en
type: doc
tags: [htmx, preview, csp, app-check]
keywords: [htmx 4, htmx-2-compat, hx-sse, rollback, self-hosting]
category: guide
---

## Opt in exactly

Chirp's htmx 4 lane is provisional and never selected by a loose range. Reuse
the existing frozen config fields with the one allowlisted pin:

```python
from chirp import App, AppConfig

app = App(AppConfig(htmx=True, htmx_version="4.0.0-beta5"))
```

Chirp injects these classic deferred scripts once, in order:

1. `dist/htmx.min.js`
2. `dist/ext/htmx-2-compat.min.js`
3. `dist/ext/hx-sse.min.js`

Every URL is pinned to `htmx.org@4.0.0-beta5`; every tag receives the same
request CSP nonce and exact tier/version metadata. A core marker already in
the document suppresses the entire managed bundle, not just the first script.

## Self-host the complete bundle

Set `htmx=False` and own all three local files. Mark their roles so
`app.check()` and DevTools can distinguish a complete preview from a silent
mixed client:

```html
<script defer src="/static/htmx.min.js"
  data-chirp="htmx" data-chirp-htmx-role="core"
  data-chirp-htmx-tier="4-preview"
  data-chirp-htmx-version="4.0.0-beta5"></script>
<script defer src="/static/htmx-2-compat.min.js"
  data-chirp="htmx-extension" data-chirp-htmx-extension="compat"
  data-chirp-htmx-tier="4-preview"
  data-chirp-htmx-version="4.0.0-beta5"></script>
<script defer src="/static/hx-sse.min.js"
  data-chirp="htmx-extension" data-chirp-htmx-extension="sse"
  data-chirp-htmx-tier="4-preview"
  data-chirp-htmx-version="4.0.0-beta5"></script>
```

Local artifact integrity remains your deployment responsibility. Chirp does
not add a configurable CDN base or infer extension versions.

## Fail before the browser

The `htmx_compatibility` contract category is an `ERROR`. It names the template
and detected line when managed and manual core would load twice, preview roles
are missing or duplicated, scripts are out of order, versions disagree, or
htmx 2 and htmx 4 SSE markup are mixed.

In debug mode, `window.ChirpHtmxDebug.getHtmxCompatibility()` reports configured
and live versions, extension roles, source URLs, duplicates, and the resulting
compatibility state. Request headers alone do not prove the browser version.

## Roll back

Return to the verified baseline and remove htmx 4-only markup:

```python
app = App(AppConfig(htmx=True, htmx_version="2.0.10"))
```

Run `app.check()` before rollout. Chirp's default and generated scaffolds stay
on 2.0.10 until the separate htmx 4 GA release gate is satisfied.
