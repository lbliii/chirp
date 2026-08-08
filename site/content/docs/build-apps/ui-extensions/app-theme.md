---
title: App-owned tokens and themes
description: Semantic CSS tokens, data-theme light/dark/system, and cookie-backed preference without a UI runtime
draft: false
weight: 36
lang: en
type: doc
tags: [theme, css, scaffold, accessibility, csp]
keywords: [tokens.css, data-theme, theme.js, light dark system, app-owned CSS]
category: guide
---

## Overview

Generated Chirp apps own their visual identity. `chirp new` copies ordinary CSS
and a small preference helper into the project — not a token registry, CSS-in-Python
API, or frontend build. The contract matches
[RFC 025](https://github.com/lbliii/chirp/blob/main/docs/rfcs/025-app-owned-ui-contracts.md).

## What the scaffold writes

```text
static/css/
  tokens.css       # semantic custom properties
  base.css         # reset + element defaults
  components.css   # reusable component styles
  patterns.css     # product compositions
  pages.css        # route-level layout
static/js/
  theme.js         # progressive enhancement (no Alpine)
  interactions.js  # empty hook for app scripts
theme.py           # cookie preference helpers
pages/_context.py  # exposes theme (+ current_path) to layouts
```

Filenames are scaffold convention. Rename or merge them freely; Chirp does not
error on different CSS paths.

## Root theme attributes

Layouts render the preference on `<html>`:

```html
<html lang="en" data-theme="{{ theme }}">
```

Allowed `data-theme` values: `light`, `dark`, `system` (default when unset).
Optional `data-skin` and `data-density` are extension points — define allowlists
in `theme.py` before emitting them.

First paint does **not** need an inline script. The server sets `data-theme` from
the cookie, and `tokens.css` maps `data-theme="system"` through
`prefers-color-scheme`. That keeps CSP `script-src` free of `unsafe-inline`.

## Preference persistence

| Posture | Authority |
| --- | --- |
| Anonymous | Same-site `chirp_theme` cookie (HttpOnly, `SameSite=Lax`) |
| Authenticated (later) | Prefer an account setting that still drives the same root attribute |

Local storage is only a cross-tab sync hint in `theme.js`. Navigation output must
not depend on a client-only preference.

The no-JavaScript path is a plain form POST to `/theme` (CSRF-protected) that
sets the cookie and redirects. With script allowed, `theme.js` updates
`data-theme` immediately on radio change, then the same form persists it.

HTMX swaps target page regions, not `<html>`, so root theme state survives
boosted navigation. Full reloads re-read the cookie.

## Customize ownership

1. Edit token values in `static/css/tokens.css`.
2. Style components next to `templates/components/` in `components.css`.
3. Keep product vocabulary in `patterns.css` / `templates/patterns/`.
4. Extend `SKINS` / `DENSITIES` in `theme.py` only with values you validate.

Do not render user-controlled CSS text. Prefer allowlisted attribute values or a
generated stylesheet with fixed property names.

## Accessibility

Scaffold CSS keeps `:focus-visible`, `forced-colors`, and
`prefers-reduced-motion` usable. Theme changes must not rely on color alone —
the control exposes text labels (Light / Dark / System).

## Related

- [[docs/reference/cli|CLI]] — `chirp new` flags
- [[docs/build-apps/ui-extensions/chirp-ui|chirp-ui]] — optional compatibility theme path
- [[docs/build-apps/ui-extensions/accessibility|Accessibility]]
