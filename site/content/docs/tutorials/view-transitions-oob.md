---
title: View Transitions + OOB — The Stable Pattern
description: Reliable pattern for combining htmx-boost, View Transitions, and OOB/SSE updates without flicker
draft: false
weight: 15
lang: en
type: doc
tags: [tutorial, htmx, view-transitions, oob, sse, patterns]
keywords: [view-transitions, oob, sse, flicker, htmx-boost, stable]
category: tutorial
---

## The Problem

When you combine **htmx-boost** (AJAX navigation), **View Transitions** (smooth animations), and **OOB swaps** (live updates via SSE or form responses), you often get:

- **Whole node tree wiped** — when an SSE/OOB update arrives, the entire content area is replaced by the fragment
- **Flicker on load** — page content flashes or briefly disappears
- **Whole content erased** — View Transitions trigger on OOB updates, animating the whole block away

These come from three specific mistakes. Fix all three and the pattern is stable.

## Root Causes

### 1. `hx-target` inheritance (whole tree wiped)

When `sse-connect` (or any element that receives SSE/WebSocket fragments) is inside a container with `hx-target` (e.g. `#main` from hx-boost), it **inherits** that target. When a fragment arrives, htmx swaps it into `#main` instead of the sse-swap element. The entire `#main` innerHTML gets replaced by the fragment — one meta div replaces the whole list.

**Fix:** Add `hx-disinherit="hx-target hx-swap"` on the `sse-connect` element so the fragment goes to the sse-swap sink, not the layout target.

### 2. `transition:true` on the container

When the swap target (e.g. `#main`) has `hx-swap="innerHTML transition:true"`, htmx wraps **every** swap into that target in the View Transitions API — including OOB swaps to its descendants. OOB updates then trigger a full-area transition: the browser captures the "old" state, applies the change, and animates. If the capture or timing is wrong, you get flicker or content disappearing.

**Fix:** Put `transition:true` only on the **links/forms that trigger navigation**, not on the container.

### 3. `view-transition-name` on a parent of OOB targets

When an element with `view-transition-name` contains (or is an ancestor of) elements that receive OOB swaps, each OOB update can trigger the View Transitions API for that named element. The browser treats the OOB change as a "transition" of the whole block — causing the full content to animate out and back in, or worse, to disappear.

**Fix:** Scope `view-transition-name` to elements that change **only on full navigation**, never on parents of OOB targets.

## The Stable Pattern

### Rule 0: SSE/WebSocket scope — outside the boost target, use `hx-disinherit`

**Preferred** — extend the Chirp boost layout (correct structure baked in). The `sse_scope` block renders **outside** `#main` so the connection persists across navigations:

```html
{% extends "chirp/layouts/boost.html" %}
{% block content %}
  <ol>...</ol>
{% endblock %}
{% block sse_scope %}
  {% from "chirp/sse.html" import sse_scope %}
  {{ sse_scope("/events") }}
{% endblock %}
```

If you place `sse_scope` inside `{% block content %}`, it gets replaced when you navigate — the connection dies and live updates stop.

**Or** manually add `hx-disinherit` and `hx-target="this"`, and place the SSE div **outside** the boost target:

```html
<div hx-ext="sse" sse-connect="/events" hx-disinherit="hx-target hx-swap">
  <div sse-swap="fragment" hx-target="this" class="sse-sink"></div>
</div>
```

The `hx-target="this"` on the sse-swap element ensures htmx correctly processes the response (including OOB swaps) when inheritance is broken.

Without this, the fragment swaps into `#main` and wipes the whole page. `chirp check` errors if you omit it.

**Placement:** Put the SSE connection **outside** the boost target (`#main`). If it's inside, navigation replaces it and the connection is lost — live updates stop until you return to that view.

**Templates with OOB fragments**: Use `{% imports %}...{% end %}` for fragment-safe imports — intent-revealing and available in `render_block()`. Top-level `{% from %}...{% import %}` also works; `{% globals %}` is a fallback for older Kida.

### Rule 1: Container — no transition, no view-transition-name

```html
<div id="main" hx-boost="true" hx-target="#main" hx-swap="innerHTML">
  <!-- Content + OOB targets live here -->
</div>
```

- `hx-swap="innerHTML"` — no `transition:true`
- No `view-transition-name` on `#main` or any ancestor of OOB targets

### Rule 2: Nav links — add transition on the trigger

**Preferred** — use the Chirp `nav_link` macro (never forget the transition attribute):

```html
{% from "chirp/nav.html" import nav_link %}
{{ nav_link("/story/123", "Story title") }}
{{ nav_link("/", "← Back", class="back") }}
```

**Or** manually add `hx-swap="innerHTML transition:true"` to each link:

```html
<a href="/story/123" hx-swap="innerHTML transition:true">Story title</a>
<a href="/" hx-swap="innerHTML transition:true">&larr; Back</a>
```

Each link that performs full-page-style navigation gets `hx-swap="innerHTML transition:true"`. The swap still targets `#main` (inherited from `hx-boost`), but the **requesting element** carries the transition flag. Navigation uses transitions; OOB updates do not.

### Rule 3: view-transition-name — only on nav-only content

```css
/* Only the content that changes on full navigation gets the transition */
#main > .story-detail {
  view-transition-name: page-content;
}
```

- List view: no `view-transition-name` (it has OOB targets: meta-lines)
- Detail view: `.story-detail` gets it (no OOB targets inside)

### Rule 4: OOB fragments — match the nav link attributes

When you OOB-swap an element that contains nav links, those links must include `hx-swap="innerHTML transition:true"` so they behave the same after the swap. Use `nav_link` with `push_url=true` for SPA-style URL updates:

```html
{% from "chirp/nav.html" import nav_link %}
<div id="meta-123" hx-swap-oob="outerHTML">
  <span class="score">42 points</span>
  {{ nav_link("/story/123", "5 comments", push_url=true) }}
</div>
```

## Reference Template

**Option A** — extend the Chirp boost layout (recommended):

```html
{% extends "chirp/layouts/boost.html" %}
{% block content %}
  {% from "chirp/nav.html" import nav_link %}
  {% if view == "list" %}
    <ol>
      {% for item in items %}
      <li>
        {{ nav_link("/item/" ~ item.id, item.title) }}
        <div id="meta-{{ item.id }}">
          <span>{{ item.score }} points</span>
          {{ nav_link("/item/" ~ item.id, "comments") }}
        </div>
      </li>
      {% endfor %}
    </ol>
  {% elif view == "detail" %}
    <div class="detail-view">
      {{ nav_link("/", "← Back", class="back") }}
      <!-- detail content -->
    </div>
  {% endif %}
{% endblock %}
{% block sse_scope %}
  {% from "chirp/sse.html" import sse_scope %}
  {{ sse_scope("/events") }}
{% endblock %}
```

**Option B** — copy this structure manually when building apps that mix navigation, view transitions, and OOB/SSE:

```html
{% from "chirp/sse.html" import sse_scope %}
{% from "chirp/nav.html" import nav_link %}
<head>
  <meta name="view-transition" content="same-origin">
  <script src="https://unpkg.com/htmx.org@2.0.4"></script>
  <script src="https://unpkg.com/htmx-ext-sse@2.2.2/sse.js"></script>
  <style>
    @view-transition { navigation: auto; }
    ::view-transition-old(page-content) { animation: fade-out 0.15s; }
    ::view-transition-new(page-content) { animation: fade-in 0.2s; }
    /* Only nav-only content — NOT the container, NOT parents of OOB targets */
    #main > .detail-view { view-transition-name: page-content; }
  </style>
</head>
<body>
  <div id="main" hx-boost="true" hx-target="#main" hx-swap="innerHTML">
    {% if view == "list" %}
      <ol>
        {% for item in items %}
        <li>
          {{ nav_link("/item/" ~ item.id, item.title) }}
          <div id="meta-{{ item.id }}">
            <span>{{ item.score }} points</span>
            {{ nav_link("/item/" ~ item.id, "comments") }}
          </div>
        </li>
        {% endfor %}
      </ol>
    {% elif view == "detail" %}
      <div class="detail-view">
        {{ nav_link("/", "← Back", class="back") }}
        <!-- detail content -->
      </div>
    {% endif %}
  </div>
  {{ sse_scope("/events") }}
  {% block oob %}
  {% if item is defined %}
  <div id="meta-{{ item.id }}" hx-swap-oob="outerHTML">
    <span>{{ item.score }} points</span>
    {{ nav_link("/item/" ~ item.id, "comments", push_url=true) }}
  </div>
  {% endif %}
  {% endblock %}
</body>
```

## Checklist for New Apps

Before shipping an app that uses htmx-boost + View Transitions + OOB/SSE:

| Check | Status |
|-------|--------|
| Use `{{ sse_scope(url) }}` or `hx-disinherit` + `hx-target="this"` on sse-swap | ☐ |
| `sse_scope` placed **outside** the boost target (`#main`) so connection persists | ☐ |
| Container (`#main` or equivalent) has `hx-swap="innerHTML"` **without** `transition:true` | ☐ |
| Every nav link (story, back, comments, etc.) has `hx-swap="innerHTML transition:true"` | ☐ |
| `view-transition-name` is only on elements that change on full nav, never on parents of OOB targets | ☐ |
| OOB fragments that contain nav links include `hx-swap="innerHTML transition:true"` on those links | ☐ |
| SSE connect sends a ping first, not an initial OOB fragment that duplicates page content | ☐ |

## When You Don't Have OOB

If your app has **no** OOB swaps (no SSE live updates, no multi-fragment form responses), you can use the simpler pattern:

```html
<div id="main" hx-boost="true" hx-target="#main" hx-swap="innerHTML transition:true">
  {% block content %}{% endblock %}
</div>
```

```css
#main { view-transition-name: page-content; }
```

No nav links need `hx-swap` overrides. The container can have `transition:true` and `view-transition-name` because nothing will trigger transitions except user clicks.

## Summary

| Scenario | Container `hx-swap` | `view-transition-name` | Nav links |
|----------|---------------------|-------------------------|-----------|
| **OOB/SSE on same page** | `innerHTML` (no transition) | Only on nav-only content | Add `hx-swap="innerHTML transition:true"` |
| **No OOB** | `innerHTML transition:true` | On container | Inherit from container |

The key: **OOB updates must not trigger View Transitions.** Scope transitions to user-initiated navigation only.
