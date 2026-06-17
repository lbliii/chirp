---
title: Fragment Blocks - Swap-Only Targets
description: When to use `{% block %}` vs `{% fragment %}` — the directive for blocks that render only as swap targets
draft: false
weight: 22
lang: en
type: doc
tags: [templates, fragments, htmx, oob, sse]
keywords: [fragment, block, fragment-only, swap target, OOB, SSE payload, kida]
category: guide
---

## Overview

Some template regions only ever appear as the answer to an htmx swap — a success banner after a form submit, an [[docs/build-apps/streaming-updates/server-sent-events|SSE event payload]], a counter that pops in on the first mutation. They are never visible when the page first loads. The `{% fragment %}` directive marks exactly these swap-only regions: their body is suppressed during a full-page render and only emits content when the region is addressed directly as a [[docs/build-apps/html-fragments/fragments|Fragment]].

## When to reach for it

The choice is between two kida directives, and one question decides it: **does the region exist on the page when it first loads?**

- `{% block name %}...{% endblock %}` — the region renders **both** inline (as part of a full page) **and** as a [[docs/build-apps/html-fragments/_index|swap target]].
- `{% fragment name %}...{% end %}` — the region renders **only** as a swap target. The body is suppressed during full-template renders and emits content only when addressed by `Fragment("page.html", "name", ...)`, the `/_frag{path}?_b=name` dispatcher, or a page shell contract.

Both directives produce the same AST node in kida — `{% fragment %}` is a `{% block %}` with a `fragment` flag set. Chirp's block metadata, OOB registry, page shell contracts, and `Fragment(...)` dispatch all treat them identically. The only difference is **what gets rendered at root**.

## The problem `{% fragment %}` solves

A gallery page has a form. On successful submit, the server returns:

```python
return Fragment("gallery.html", "demo_form_ok", form=form)
```

`demo_form_ok` is a block like:

```kida
{% block demo_form_ok %}
<div class="ok">Form accepted: {{ form.name }}</div>
{% endblock %}
```

So far so good — except that when the page first loads (full `Template` render), this block is rendered inline too. On first paint you see "Form accepted: " (with no name) *before* the user has done anything. The fix most apps reach for is a guard:

```kida
{% block demo_form_ok %}
{% if form is defined %}
<div class="ok">Form accepted: {{ form.name }}</div>
{% endif %}
{% endblock %}
```

This works, but every swap-only block now ships a stanza of workaround boilerplate. The **intent** is "this block only renders as a swap target" — say that directly:

```kida
{% fragment demo_form_ok %}
<div class="ok">Form accepted: {{ form.name }}</div>
{% end %}
```

During `Template("gallery.html", ...)` the body is suppressed — zero characters emitted, no `is defined` guards, no undefined variables. During `Fragment("gallery.html", "demo_form_ok", form=form)` the block renders exactly as before.

## Decision table

| Situation | Directive |
|-----------|-----------|
| A region that is visible on page load **and** updated by htmx swaps | `{% block %}` |
| A form that re-renders with errors on 422 | `{% block %}` (it *is* on the page initially — just re-rendered in place) |
| A success banner shown only after the POST succeeds | `{% fragment %}` |
| An SSE event payload (each yielded `Fragment`) | `{% fragment %}` |
| An OOB swap target where the initial state is empty (e.g. a counter that appears on first mutation) | `{% fragment %}` |
| A deferred `Suspense` slot (placeholder → resolved) | `{% block %}` — the shell still renders the placeholder. See [Suspense caveat](#suspense-deferred-blocks) below. |

:::{tip} Rule of thumb
Ask whether the region exists on page load. If yes, use `{% block %}`. If no, use `{% fragment %}`.
:::

## Full example: returns gallery

[`examples/standalone/returns_gallery/templates/gallery.html`](https://github.com/lbliii/chirp/blob/main/examples/standalone/returns_gallery/templates/gallery.html) is the reference consumer. It addresses several kinds of region:

- `demo_fragment`, `demo_page`, `demo_oob_primary` — inline-rendered and swap-addressable.
- `demo_form` — inline-rendered, also the re-render target on 422.
- `demo_form_ok`, `demo_sse_item`, `demo_mutation_counter` — swap-only regions that today still use a `{% block %}` plus a `{% if ... is defined %}` / `| default(...)` guard.

The swap-only blocks in that template are exactly the candidates for `{% fragment %}`: each one ships a guard whose only job is to suppress its body on first paint. Read `app.py` alongside the template to see which routes target which blocks, then apply the [migration recipe](#migration-recipe) below.

## Suspense deferred blocks

:::{warning} Do not convert Suspense slots to `{% fragment %}`
[[docs/build-apps/streaming-updates/_index|Suspense]] renders the shell first, then streams each deferred block as an OOB swap once its awaitable resolves. A deferred slot **is** on the page at load — it shows a skeleton. Mark it `{% fragment %}` and the shell renders an empty div instead, silently defeating the shell-first UX.
:::

Use a regular `{% block %}` with a loading check. The shell sets each deferred key to a sentinel value, so test it with `{% if key is deferred %}` rather than a bare truthiness check:

```kida
{% block stats %}
  {% if stats is deferred %}
    <div class="skeleton"></div>
  {% else %}
    <div>{{ stats.users }} users</div>
  {% endif %}
{% endblock %}
```

See [[docs/build-apps/streaming-updates/_index|Streaming & updates]] for the full deferred-block pattern.

## Migration recipe

Convert a `{% block %}` + `is defined` workaround to `{% fragment %}`. The guard stanza disappears:

::::{tab-set}
:::{tab-item} Before
```kida
{% block notification %}
{% if msg is defined %}
<div class="toast">{{ msg }}</div>
{% endif %}
{% endblock %}
```
:::{/tab-item}

:::{tab-item} After
```kida
{% fragment notification %}
<div class="toast">{{ msg }}</div>
{% end %}
```
:::{/tab-item}
::::{/tab-set}

::::{steps}
:::{step} Rename the tags
Change `{% block foo %}` to `{% fragment foo %}` and `{% endblock %}` to `{% end %}`.
:::{/step}
:::{step} Drop the guard
Remove the `{% if ... is defined %}` or `{% if ... %}` truthiness guard that was protecting the block body from full-render exposure.
:::{/step}
:::{step} Drop default filters
Remove `| default(...)` filters on variables that only exist in the fragment's context.
:::{/step}
:::{step} Decide on the placeholder
If the block previously rendered a placeholder inline (e.g. `"Counter: 0"`), ask whether an empty swap target is acceptable on page load. If yes, convert to `{% fragment %}`. If no, keep `{% block %}` and leave the default filter in place.
:::{/step}
::::{/steps}

Run `rg '{% if .* is defined %}'` afterwards — any remaining hits are either legitimate conditionals (e.g. error display) or missed workarounds. The error-display case is cleaner with `.get(...)`:

```kida
{% if _errors.get("name") %}<span class="err">{{ _errors.get("name") }}</span>{% endif %}
```

## What chirp does for you

Chirp treats fragment blocks identically to regular blocks everywhere — block metadata, dispatch, OOB swaps, and [[docs/quality/contracts-debugging/categories|contract checks]]. You wire a fragment block exactly as you would a regular one, and typos in fragment names still get caught at `app.check()` time.

:::{dropdown} Advanced: what the framework does with fragment blocks
- **Block metadata** (`template.block_metadata()`) surfaces fragment blocks identically to regular blocks — no consumer needs to know the difference.
- **`/_frag{path}?_b=name`** dispatcher resolves fragment blocks.
- **Page shell contracts** (`PageShellContract.targets`) accept fragment blocks as required or optional targets.
- **[[docs/quality/contracts-debugging/oob-registry|OOB registry]]** (`app.register_oob_region(...)`) accepts fragment block names.
- **Contract checks:**
  - `check_unreachable_blocks` does **not** flag fragment blocks — they are unreachable from composition roots *by design*.
  - `check_fragment_target_orphans` and `check_page_shell_contracts` walk `block_metadata()` and catch typos in fragment block names the same way.
  - `check_sse_event_crossref` infers targets from literal `Fragment(target=...)` calls and reports mismatches with `sse-swap=...` attributes.
:::{/dropdown}

## See also

:::{note} See also
- [[docs/build-apps/html-fragments/fragments|Fragment]] — the return type that addresses a swap-only block
- [[docs/quality/contracts-debugging/oob-registry|OOB Registry & Fail-Loud Rendering]]
- [[docs/build-apps/ui-extensions/app-shell|App Shells]]
- [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]] — each yielded `Fragment` targets a swap-only block
- [kida `{% fragment %}` directive docs](https://lbliii.github.io/kida/docs/directives/fragment/)
:::
