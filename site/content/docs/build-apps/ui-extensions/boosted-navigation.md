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

## Overview

Boosted navigation turns an ordinary `<a href="...">` click into an htmx swap.
The page never full-reloads: htmx fetches the destination URL, pulls out the
matching block, and replaces one DOM node. The shell — topbar, sidebar, footer —
stays mounted, and only the content outlet re-renders.

You opt in with htmx's `hx-boost="true"`. Chirp's job is to render the right
block on the way back and to fail safely when a link can't swap into the current
shell.

## When to reach for it

Reach for boosted navigation when links inside a
[[docs/build-apps/ui-extensions/app-shell|persistent app shell]] should feel
like an SPA without you writing `hx-*` attributes on every link. Return a
[[docs/about/core-concepts/return-values|`Page`]] and Chirp picks the wide block
for a boosted click and the narrow block for an in-page fragment swap
automatically.

| Request type | `HX-Boosted` | Block rendered |
|---|---|---|
| Full page load | absent | full template (composed into the layout) |
| Boosted link click | `true` | the wide `page_block_name` (e.g. `page_root`) |
| Narrow fragment (form post, search input) | absent; `HX-Request: true` | the narrow `block_name` (e.g. `page_content`) |

## Minimal working example

Return `Page(...)` with two block names. The first is the narrow block for
in-page fragment swaps; `page_block_name` is the wider, fragment-safe root used
for a boosted navigation. Chirp reads the `HX-Boosted` header and chooses.

```python
def get(request: Request) -> Page:
    query = normalize_query(request.query.get("q"))
    group = normalize_query(request.query.get("group"))
    return Page(
        "contacts/page.html",
        "page_content",
        page_block_name="page_root",
        **page_context(query, group),
    )
```

*Source: [`examples/chirpui/contacts_shell/pages/contacts/page.py`](https://github.com/lbliii/chirp/blob/main/examples/chirpui/contacts_shell/pages/contacts/page.py).*

That single handler serves three callers: a full page load, a boosted link
click, and a narrow in-page swap. See the
[[docs/examples/contacts-shell|contacts shell example]] for the full app.

## The contract

A boosted `GET` is checked against three rules. If any rule can't be met, Chirp
emits an `HX-Redirect` so the browser performs a real navigation — it never
renders a broken fragment.

::::{steps}
:::{step} One block matches `HX-Target`
The destination route's layout chain must define a block mapped to the requested
target id. Chirp normalizes the header once at the request layer, so `#main` and
`main` resolve to the same id.
:::{/step}
:::{step} The destination is reachable from the current shell
If the link crosses a shell boundary — say, marketing site to dashboard app —
the destination layout isn't mounted, so Chirp redirects instead of swapping.
:::{/step}
:::{step} The response body is a fragment, not a full page
A `<!DOCTYPE>` in a fragment response means the handler bypassed `Page(...)` or
returned the wrong `Template(...)`. In debug mode Chirp warns you — see
[Debug warnings](#debug-warnings).
:::{/step}
::::{/steps}

:::{note}
A boosted `GET` never returns a 500 on a malformed target. Chirp either renders
a valid fragment or emits a redirect.
:::

## Choosing the right link helper

Which attributes a link needs depends on whether it stays inside the current
shell, crosses into another, or leaves the app.

:::{list-table}
:header-rows: 1

* - Link destination
  - Use
  - What you get
* - Same shell, in-outlet
  - `route_link_attrs()` (chirp-ui) or a bare `<a>` inside a boosted region
  - `hx-boost="true"` plus the inherited target
* - Crosses shell / layout domain
  - `swap_attrs(href)`
  - A framework-resolved `hx-target`, or an `HX-Redirect` at request time
* - External / download / anchor
  - `hx-boost="false"`
  - Full navigation; htmx leaves the element alone
:::

### In-shell links — just use `<a href>`

Inside an app-shell layout (or any boosted outlet), `hx-boost="true"` is set on
the outlet itself. Child `<a>` tags inherit it, so no per-link markup is needed:

```html
<a href="/contacts">Contacts</a>
<a href="/contacts/42">View</a>
```

chirp-ui's `sidebar_link()` emits `route_link_attrs()` for links *outside* the
content outlet (the sidebar is not inside the boosted region), so those links
still participate in swaps.

### Cross-shell links — use `swap_attrs`

When the destination lives in a different layout domain — for example, linking
from the marketing site root into the dashboard at `/app/*` — hand the href to
`swap_attrs` and let the framework pick the target:

```html
<a href="/app/inbox" {{ swap_attrs("/app/inbox") | html_attrs }}>Open inbox</a>
```

`swap_attrs` walks the current and destination layout chains, finds the nearest
shared ancestor outlet, and returns `{"hx-target": "#<outlet>", "hx-boost":
"true"}`. If no shared ancestor exists, the request-time check redirects: the
link still works, the browser just does a real navigation.

### Opt out with `hx-boost="false"`

Use this for elements htmx must not touch:

```html
<a href="/export.csv" hx-boost="false" download>Download CSV</a>
<a href="https://example.com" hx-boost="false">External site</a>
<a href="#section" hx-boost="false">Jump to section</a>
```

## Cross-shell redirects

:::{since} 0.5
A boosted click crossing a shell boundary emits `HX-Redirect` and triggers a real
navigation, rather than swapping a fragment into an outlet the destination layout
never mounts.
:::

A boosted click that crosses a shell boundary cannot render into the current
outlet, because the destination layout is not mounted. Chirp emits
`HX-Redirect: <destination>` and htmx performs a real navigation:

```text
Scenario: user clicks /app/inbox from /marketing/about
Current shell: marketing (site-content outlet)
Destination:   app dashboard (main outlet)
Result:        HX-Redirect → browser fetches /app/inbox as a full page
```

Apps without any app shell pass through untouched — there is no shell boundary
to cross. You don't configure this branch; the one thing you act on is reading
the normalized target via `request.htmx_target_id` in any custom code path.

:::{dropdown} Advanced: HX-Target normalization and how redirects are decided
The `HX-Target` header arrives as `#main` or `main`, depending on how the sending
element was declared. Chirp strips the leading `#` once, at the request layer:

```python
request.htmx.target          # → "#main"   (raw header)
request.htmx.target_id       # → "main"    (normalized)
request.htmx_target_id       # → "main"    (convenience alias)
```

All framework code — fragment target resolution, render-plan building,
cross-shell redirect logic — consumes the normalized form, and so should your
code. The raw `.target` is kept only for logging. The registries normalize
defensively, so you can pass either form when registering or looking up.

The redirect is decided in three places:

1. **Inconsistent setup** — a shell is configured but the route or fragment-target
   registry is missing. Redirect rather than render against partial metadata.
2. **No shared ancestor** — the current and destination layout chains both have
   layouts but share no navigation outlet. Redirect.
3. **Target mismatch** — the computed swap target does not match the client's
   `HX-Target`. Redirect.
:::{/dropdown}

## Debug warnings

When `AppConfig(debug=True)`, the `DebugFragmentValidator` middleware inspects
buffered fragment responses and logs a warning when it finds patterns that mean
a swap is broken. It runs only when the render intent is `fragment` (or
`unknown` on an htmx request); streaming responses, non-HTML content, and
full-page intents pass through. It is on by default (`debug_fragment_validator`
defaults to `True`).

:::{warning}
The bite that catches everyone: returning `Template(...)` from a boosted handler
leaks a full-page `<!DOCTYPE>` document into the content outlet, so the fragment
appears but the shell visibly jumps or duplicates. Return `Page(...)` (or
`Fragment(...)`) instead. In debug mode the validator warns; in production it is
silent, so trust the warning.
:::

The validator flags two patterns:

| Pattern | Meaning | Fix |
|---|---|---|
| `<!DOCTYPE>` in fragment body | A full page rendered into an outlet | Return `Page(...)` or `Fragment(...)`, not `Template(...)` |
| A registered shell-region id appearing more than once | A shell region is duplicated in the fragment | Remove the duplicate block; OOB regions own their DOM id (see [[docs/quality/contracts-debugging/oob-registry|OOB fail-loud policy]]) |

To silence a warning, fix the handler first — the warning is almost always
correct. If your app intentionally renders pre-serialized fragments with repeated
ids, opt out globally with `AppConfig(debug_fragment_validator=False)`.

:::{dropdown} Advanced: fail the CI build on fragment leakage
To make leakage fail a test run instead of just logging, construct the middleware
directly with `strict=True`:

```python
from chirp.middleware.debug_fragment_validator import DebugFragmentValidator

# CI-only: fail the build on fragment leakage
app.add_middleware(DebugFragmentValidator(oob_registry, strict=True))
```

Strict mode raises `FragmentValidationError` instead of logging. The error
propagates to the app's error handler and surfaces as a 500 in tests — visible
rather than quiet.
:::{/dropdown}

## Troubleshooting

:::{list-table}
:header-rows: 1

* - Symptom
  - Likely cause
* - Link does a full reload instead of swapping
  - `hx-boost="false"` is set on an ancestor, or the `<a>` is outside the boosted outlet
* - Fragment appears but the shell jumps
  - The handler returned `Template(...)` (full page) instead of `Page(...)`; the debug validator warns
* - Cross-shell click does a full navigation
  - Expected — the destination is in another shell, so Chirp emits `HX-Redirect`
* - Page renders twice / duplicate ids
  - A shell-region block is duplicated in the fragment; the validator warns on registered ids
* - `HX-Target: #main` works but `HX-Target: main` fails (or the reverse)
  - A custom code path forgot to normalize; use `request.htmx_target_id`
:::

:::{note} See also
- [[docs/build-apps/ui-extensions/app-shell|App shells]] — building the shell that hosts boosted links
- [[docs/build-apps/ui-extensions/shells|Shells]] — what is and is not a shell, and the `hx-select` distinction
- [[docs/build-apps/ui-extensions/ui-layers|UI layers and shell regions]] — `swap_attrs` and shell regions, layout scope comments
- [[docs/quality/contracts-debugging/oob-registry|OOB registry]] — registering shell regions and the fail-loud policy
- [[docs/build-apps/pages-navigation/filesystem-routing|Filesystem routing]] — `_layout.html` outlet/target/domain declarations
:::

:::{related}
:::
