---
title: View Transitions + OOB — The Stable Pattern
description: Add crossfade animations to boosted navigation without OOB or SSE updates wiping the page — by extending Chirp's boost layout
draft: false
weight: 15
lang: en
type: doc
tags: [tutorial, htmx, view-transitions, oob, sse, patterns]
keywords: [view-transitions, oob, sse, flicker, htmx-boost, stable, nav_link, sse_scope]
category: tutorial
---

## What this solves

View Transitions add a smooth crossfade when an htmx-boosted link swaps the
page. The catch: those same transitions — plus htmx's attribute inheritance —
can flicker or wipe your content the moment an
[[docs/quality/contracts-debugging/oob-registry|out-of-band (OOB) swap]] or
[[docs/build-apps/streaming-updates/server-sent-events|SSE live update]] arrives.
The browser tries to animate a live update as if it were a navigation, and the
animation captures the wrong DOM.

The stable pattern is one rule: **transitions are for user-initiated navigation
only; OOB and SSE updates stay out of the transition path.** This tutorial is for
a hypermedia practitioner who already uses
[[docs/build-apps/ui-extensions/boosted-navigation|htmx-boost navigation]],
[[docs/about/core-concepts/return-values|`Fragment`/`OOB` return types]], and SSE,
and wants them to coexist with animations.

The short version: extend Chirp's boost layout and use the `nav_link` and
`sse_scope` macros. They bake the correct structure in. The longer version —
*why* it breaks and how to wire it by hand — is collapsed below for when you need it.

:::{note}
Extending `chirp/layouts/boost.html` and using the `nav_link` / `sse_scope`
macros gives you all of this for free. The hand-wiring rules further down are
only for apps that can't extend the layout.
:::

## The happy path

Three steps. Extend the layout, point the `sse_scope` block at your event route,
and use `nav_link` for every link that navigates.

::::{steps}
:::{step} Extend the boost layout

`chirp/layouts/boost.html` ships the correct structure: no transition on the
`#main` container, content wrapped in `<div id="page-content">`, and
`hx-select="#page-content"` so boosted responses pull only the content region.

```html
{% extends "chirp/layouts/boost.html" %}
{% block content %}
  <ol>...</ol>
{% end %}
```

:::{/step}
:::{step} Override the `sse_scope` block for live updates

The layout renders the `sse_scope` block **outside** `#main`, so the connection
survives navigations. The `sse_scope` macro wraps the connection with
`hx-disinherit="hx-target hx-swap"` so incoming fragments land in the SSE sink
instead of replacing the whole content area.

```html
{% block sse_scope %}
  {% from "chirp/sse.html" import sse_scope %}
  {{ sse_scope("/events") }}
{% end %}
```

If you put `sse_scope` inside `{% block content %}` instead, navigation replaces
it and the connection dies.

:::{/step}
:::{step} Use `nav_link` for navigation

The `nav_link` macro emits `<a ... hx-swap="innerHTML transition:true">`, so the
transition flag rides on the *link*, not the container. Navigation animates; OOB
updates don't.

```html
{% from "chirp/nav.html" import nav_link %}
{{ nav_link("/story/123", "Story title") }}
{{ nav_link("/", "← Back", class="back") }}
{{ nav_link("/story/123", "5 comments", push_url=true) }}  {# SPA URL update #}
```

:::{/step}
::::{/steps}

That's the whole pattern. When you OOB-swap a region that contains links, render
those links with `nav_link` too so they keep transitioning after the swap.

## The footgun this prevents

:::{danger} Never put `view-transition-name` (or `transition:true`) on a parent of an OOB target
A `view-transition-name` in CSS — or `hx-swap="...transition:true"` — on the
`#main` container or any ancestor of an OOB/SSE target makes the browser animate
the **whole region** every time a live update lands. Live content fades out and
back in, flickers, or disappears.

Scope `view-transition-name` to content that changes **only on full navigation**
(e.g. a detail view with no OOB targets inside it), and keep `transition:true` on
nav links, never on the container.

`chirp check` catches this: a broad container with `transition:true` or a
`view-transition-name` on an OOB/SSE region raises a **WARNING** in the
`view_transition_scope` category. An `sse-connect` left inside a broad
`hx-target` scope without `hx-disinherit` (or `hx-target="this"`) is an **ERROR**
in the `sse_scope` category. See
[[docs/quality/contracts-debugging/categories|chirp check contract categories]].
:::

## Reference template

A list view (has OOB targets — the per-item meta line) and a detail view (no OOB
targets, so it gets the transition name), wired through the boost layout:

```html
{% extends "chirp/layouts/boost.html" %}
{% block content %}
  {% from "chirp/nav.html" import nav_link %}
  {% if view == "list" %}
    <ol>
      {% for item in items %}
      <li>
        {{ nav_link("/item/" ~ item.id, item.title) }}
        <div id="meta-{{ item.id }}">  {# OOB target — no view-transition-name above it #}
          <span>{{ item.score }} points</span>
          {{ nav_link("/item/" ~ item.id, "comments") }}
        </div>
      </li>
      {% end %}
    </ol>
  {% elif view == "detail" %}
    <div class="detail-view">  {# nav-only — safe to animate #}
      {{ nav_link("/", "← Back", class="back") }}
      <!-- detail content -->
    </div>
  {% end %}
{% end %}
{% block sse_scope %}
  {% from "chirp/sse.html" import sse_scope %}
  {{ sse_scope("/events") }}
{% end %}
{% block head_style %}
  /* Only the nav-only detail view gets a transition name */
  #page-content > .detail-view { view-transition-name: page-content; }
{% end %}
```

The OOB fragment you stream back keeps its links on `nav_link`:

```html
{% from "chirp/nav.html" import nav_link %}
<div id="meta-{{ item.id }}" hx-swap-oob="outerHTML">
  <span class="score">{{ item.score }} points</span>
  {{ nav_link("/item/" ~ item.id, "comments", push_url=true) }}
</div>
```

## Ship checklist

Before shipping an app that combines boosted navigation, View Transitions, and
OOB/SSE updates:

:::{list-table}
:header-rows: 1

* - Check
  - Why
* - Use `{{ sse_scope(url) }}` (or `hx-disinherit` + `hx-target="this"` on the sse-swap element)
  - Without it, SSE fragments inherit `hx-target` and wipe `#main` — a `chirp check` ERROR.
* - Keep the `sse_scope` block **outside** the boost target
  - Inside `#main`, navigation replaces it and the connection drops.
* - Container has `hx-swap="innerHTML"` **without** `transition:true`
  - `transition:true` on the container animates OOB swaps too.
* - Every navigation link uses `nav_link` (or carries `hx-swap="innerHTML transition:true"`)
  - The transition flag belongs on the trigger, not the container.
* - `view-transition-name` only on content that changes on full navigation
  - Never on a parent of an OOB/SSE target — a `chirp check` WARNING.
* - OOB fragments that contain links render them with `nav_link`
  - So they keep transitioning identically after the swap.
:::

## When you have no OOB or SSE

If your app has **no** OOB swaps and **no** SSE updates,
[[docs/build-apps/ui-extensions/app-shell|the chirp-ui app shell]] handles
transitions for you: extend its layout, navigate with ordinary links, and the
shell's default crossfade applies. No per-link attributes, no custom CSS.

```html
{% extends "chirpui/app_shell_layout.html" %}
{% block content %}
  <a href="/page-2">Next page</a>  {# boosted navigation inherited from the shell #}
{% end %}
```

## How it breaks, and wiring it by hand

The macros are the answer for almost every app. Open these only if you're
debugging the mechanics or building a layout you can't extend from
`chirp/layouts/boost.html`.

:::{dropdown} How it breaks: the three failure modes

**1. `hx-target` inheritance wipes the whole tree.** When an `sse-connect`
element sits inside a container with `hx-target` (e.g. `#main` from `hx-boost`),
it *inherits* that target. An incoming fragment swaps into `#main` instead of the
SSE sink — one small fragment replaces your entire list. Fix: `hx-disinherit="hx-target hx-swap"`
on the `sse-connect` element (this is exactly what `sse_scope` emits).

**2. `transition:true` on the container animates OOB swaps.** When the swap
target has `hx-swap="innerHTML transition:true"`, htmx wraps *every* swap into
that target — including OOB swaps to its descendants — in the View Transitions
API. OOB updates then trigger a full-area transition with the wrong captured
state, producing flicker or vanishing content. Fix: put `transition:true` on the
links that navigate, not on the container (this is what `nav_link` does).

**3. `view-transition-name` on a parent of OOB targets animates the block.** When
a named element is an ancestor of OOB targets, each OOB update triggers the View
Transitions API for that named element. The browser treats the OOB change as a
transition of the whole block — animating it out and back in, or making it
disappear. Fix: scope `view-transition-name` to content that changes only on full
navigation.
:::

:::{dropdown} Wiring it by hand (without the macros)

This is a simplified illustration, not a drop-in replacement for the layout — the
real `chirp/layouts/boost.html` also ships the `<div id="page-content">` wrapper
and `hx-select="#page-content"` that make boosted responses extract only the
content region. Match those if you need identical behavior.

**SSE scope** — outside the boost target, with inheritance broken:

```html
<div hx-ext="sse" sse-connect="/events" hx-disinherit="hx-target hx-swap">
  <div sse-swap="message" hx-target="this" class="sse-sink"></div>
</div>
```

`hx-target="this"` on the sse-swap element ensures htmx processes the response
(including its OOB swaps) once inheritance is broken. Place this **outside**
`#main` so navigation never replaces it.

**Container** — no transition, no `view-transition-name`:

```html
<div id="main" hx-boost="true" hx-target="#main" hx-swap="innerHTML">
  <!-- content + OOB targets live here -->
</div>
```

**Nav links** — the transition flag on the trigger:

```html
<a href="/story/123" hx-swap="innerHTML transition:true">Story title</a>
```

The swap still targets `#main` (inherited from `hx-boost`); the requesting element
carries the transition flag.

**CSS** — name only nav-only content:

```css
@view-transition { navigation: auto; }
::view-transition-old(page-content) { animation: fade-out 0.15s; }
::view-transition-new(page-content) { animation: fade-in 0.2s; }
/* NOT the container, NOT a parent of any OOB target */
#main > .detail-view { view-transition-name: page-content; }
```
:::

:::{note} See also
- [[docs/build-apps/ui-extensions/boosted-navigation|Boosted navigation]] — how hx-boost swaps work and the `hx-select` mechanics this builds on.
- [[docs/build-apps/streaming-updates/server-sent-events|Server-sent events]] — the SSE wire format and `EventStream` return type.
- [[docs/quality/contracts-debugging/oob-registry|OOB registry]] — registering OOB regions and the fail-loud policy.
- [[docs/quality/contracts-debugging/categories|Contract categories]] — what `chirp check` flags for `sse_scope` and `view_transition_scope`.
:::
