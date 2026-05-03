---
title: Boosted Navigation
description: How hx-boost swaps work in Chirp, when they redirect, and the debug warnings that catch silent failures
draft: false
weight: 37
lang: en
type: doc
tags: [htmx, hx-boost, navigation, app-shell, swap-attrs]
keywords: [hx-boost, HX-Target, boosted, cross-shell, swap_attrs, route_link_attrs, debug fragment validator]
category: guide
---

Also read: **[App Shells](/chirp/docs/guides/app-shell/)** (how shells host boosted links) and
**[UI layers & shell regions](/chirp/docs/guides/ui-layers/)** (the `swap_attrs` global, layout
scope comments).

## What Boosted Navigation Is

`hx-boost="true"` turns plain `<a href="...">` clicks into htmx swaps. The
browser never full-reloads; htmx fetches the destination URL, extracts the
fragment referenced by `hx-target`, and replaces the matching DOM node. The
shell (topbar, sidebar, footer) stays mounted — only the outlet re-renders.

Chirp recognizes boosted requests via the `HX-Boosted` header and renders the
wide page block (typically `page_root`), not the narrow fragment block. Return
`Page(...)` and Chirp picks the correct block automatically:

```python
def get(request: Request) -> Page:
    return Page(
        "contacts/page.html",
        "page_content",           # narrow — for in-page fragment swaps
        page_block_name="page_root",  # wide — for boosted navigation
        contacts=load_contacts(),
    )
```

| Request type | `HX-Boosted` | Block rendered |
|---|---|---|
| Full page load | absent | full template (inherits from layout) |
| Boosted link click | `true` | `page_root` |
| Narrow fragment (form post, search input) | absent; `HX-Request: true` | `page_content` |

## The Contract

A boosted GET has three rules. If any of them break, the framework redirects
instead of rendering a broken fragment.

1. **One fragment matches `HX-Target`.** The destination route's layout chain
   must define a block mapped to the requested target id. Chirp normalizes the
   header once at the request layer — `#main` and `main` are the same.
2. **The destination is reachable from the current shell.** If the link
   crosses shell boundaries (e.g. marketing site → dashboard app), Chirp
   emits `HX-Redirect` so the browser performs a real navigation and the new
   shell can mount.
3. **The response body is a fragment, not a full page.** A `<!DOCTYPE>` in a
   fragment response means the handler bypassed `Page(...)` or returned the
   wrong `Template(...)`. In debug mode, Chirp warns; see
   [Debug warnings](#debug-warnings).

Invariant: **a boosted GET never 500s on a malformed target.** The framework
either renders a valid fragment or emits a redirect.

## Boundary Decision Tree

Which helper emits which attributes depends on whether the link stays inside
the current shell, crosses into another, or leaves the app entirely.

| Link destination | Use | What you get |
|---|---|---|
| Same shell, in-outlet | `route_link_attrs()` (chirp-ui) or bare `<a>` inside a boosted region | `hx-boost="true"` + inherited target |
| Crosses shell / layout domain | `swap_attrs(href)` | Framework-resolved `hx-target` (broader scope) or an `HX-Redirect` path |
| External / download / anchor | `hx-boost="false"` | Full navigation; htmx leaves the element alone |

### In-shell links — just use `<a href>`

Inside `app_shell_layout.html` (or any boosted outlet), `hx-boost="true"` is
set on the outlet itself. Child `<a>` tags inherit it. No per-link markup
needed:

```html
<a href="/contacts">Contacts</a>
<a href="/contacts/42">View</a>
```

chirp-ui's `sidebar_link()` emits `route_link_attrs()` for links *outside*
`#main` (the sidebar is not inside the boosted region), so they still
participate in swaps.

### Cross-shell links — use `swap_attrs`

When the destination lives in a different layout domain — e.g. linking from
the marketing site root to the dashboard `/app/*` — hand the href to
`swap_attrs` and let the framework pick the right target:

```html
<a href="/app/inbox" {{ swap_attrs("/app/inbox") | html_attrs }}>Open inbox</a>
```

`swap_attrs` walks the current and destination layout chains, finds the
nearest shared ancestor outlet, and returns `{"hx-target": "#<outlet>",
"hx-boost": "true"}`. If no shared ancestor exists (truly cross-shell), the
framework will redirect at request time — the link still works, the browser
just performs a real navigation.

### Opt out with `hx-boost="false"`

Use this for elements htmx must not touch:

```html
<a href="/export.csv" hx-boost="false" download>Download CSV</a>
<a href="https://example.com" hx-boost="false">External site</a>
<a href="#section" hx-boost="false">Jump to section</a>
```

## HX-Target Normalization

The `HX-Target` header can arrive as `#main` or `main` depending on how the
sending element was declared. Chirp strips the leading `#` **once**, at the
request layer:

```python
request.htmx.target          # → "#main"   (raw header)
request.htmx.target_id       # → "main"    (normalized)
request.htmx_target_id       # → "main"    (convenience alias)
```

All framework code — fragment target resolution, render plan building,
cross-shell redirect logic — consumes the normalized form. Application code
should too; the raw `.target` is only kept for logging and debugging.

Registries (`FragmentTargetRegistry`, `OOBRegistry`) normalize defensively on
the public API, so you can pass either form when registering or looking up.

## Cross-Shell Redirects

A boosted click that crosses a shell boundary cannot render correctly into
the current outlet — the destination layout is not mounted. When this
happens, Chirp emits `HX-Redirect: <destination>` and htmx performs a real
navigation:

```
Scenario: user clicks /app/inbox from /marketing/about
Current shell: marketing (site-content outlet)
Destination:   app dashboard (main outlet)
Result:        HX-Redirect → browser fetches /app/inbox as a full page
```

The framework detects this in three places:

1. **Inconsistent setup** — `swap_scope_map` configured but registries are
   `None`. Redirect rather than crash.
2. **No shared ancestor** — `common_navigation_prefix_len` between the
   current and destination layout chains is zero (both chains exist but share
   no outlet). Redirect.
3. **Target mismatch** — the destination route cannot satisfy the requested
   `HX-Target` (existing logic; preserved).

Apps without any app-shell (`swap_scope_map` empty) pass through untouched —
there is no shell boundary to cross.

## Debug Warnings

When `AppConfig(debug=True)`, the `DebugFragmentValidator` middleware
inspects buffered fragment responses and logs a WARNING when it finds
patterns that indicate a broken swap:

| Pattern | Meaning | Fix |
|---|---|---|
| `<!DOCTYPE>` in fragment body | A full page was rendered into an outlet | Return `Page(...)` or `Fragment(...)` instead of `Template(...)` |
| `id="<oob-target-id>"` appearing > 1 time | Shell region is duplicated in the fragment | Remove the duplicate block; OOB regions own their DOM id |

The validator only runs when `render_intent="fragment"` (or `"unknown"` on an
htmx request — same skip rule as `HTMLInject`). Streaming responses, non-HTML
content, and full-page intents pass through unchanged.

### Silencing warnings

Two options, in order of preference:

1. **Fix the handler.** The warning is almost always correct — a fragment
   really did leak full-page markup or a duplicate id.
2. **Opt out globally.** If your app renders pre-serialized fragments with
   intentional id repetition, set
   `AppConfig(debug_fragment_validator=False)`.

### Strict mode (CI)

For CI, construct the middleware directly with `strict=True`:

```python
from chirp.middleware.debug_fragment_validator import DebugFragmentValidator

# CI-only: fail the build on fragment leakage
app.add_middleware(DebugFragmentValidator(oob_registry, strict=True))
```

Strict mode raises `FragmentValidationError` instead of logging, which
propagates to the app's error handler and becomes a 500 in tests — visible
rather than quiet.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Link does a full reload instead of swapping | `hx-boost="false"` is set on an ancestor, or the `<a>` is outside the boosted outlet |
| Fragment appears but the shell jumps | Handler returned `Template(...)` (full page) instead of `Page(...)` — debug validator should warn |
| Cross-shell click 500s | Registries inconsistent — check `app.check()` output; Sprint 2 added redirect, but an older version passed through |
| Page renders twice / duplicate ids | OOB region block duplicated in the fragment — debug validator warns on registered ids |
| `HX-Target: #main` works but `HX-Target: main` fails (or vice versa) | Custom code path forgot to normalize; use `request.htmx_target_id` |

## Related

- [[docs/guides/shells|Shells]] — the three shells you can extend, the `hx-select` distinction, and what is *not* a shell
- [[docs/guides/app-shell|App Shells]] — building the shell that hosts boosted links
- [[docs/guides/ui-layers|UI layers & shell regions]] — `swap_attrs`, layout scope comments, `{# domain: #}`
- [[docs/guides/oob-registry|OOB Registry]] — registering shell regions and the fail-loud policy for missing blocks
- [[docs/routing/filesystem-routing|Filesystem routing]] — `_layout.html` outlet/target/domain declarations
