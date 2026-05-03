---
title: Fragment Blocks — Swap-Only Targets
description: When to use `{% block %}` vs `{% fragment %}` — the directive for blocks that render only as swap targets
draft: false
weight: 32
lang: en
type: doc
tags: [templates, fragments, htmx, oob, sse]
keywords: [fragment, block, fragment-only, swap target, OOB, SSE payload, kida]
category: guide
---

## TL;DR

Use `{% block name %}...{% endblock %}` when the region renders **both** inline (as part of a full page) **and** as a swap target.

Use `{% fragment name %}...{% end %}` when the region renders **only** as a swap target — success banners after a form submit, SSE event payloads, OOB-only counters. The body is **suppressed during full-template renders** and only emits content when addressed by `Fragment("page.html", "name", ...)`, the `/_frag{path}?_b=name` dispatcher, or a page shell contract.

Both directives produce the same AST node in kida; chirp's block metadata, OOB registry, page shell contracts, and `Fragment(...)` dispatch all treat them identically. The only difference is **what gets rendered at root**.

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

Rule of thumb: **ask whether the region exists on page load.** If yes → `{% block %}`. If no → `{% fragment %}`.

## Full example: returns gallery

[`examples/standalone/returns_gallery/templates/gallery.html`](https://github.com/lbliii/chirp/blob/main/examples/standalone/returns_gallery/templates/gallery.html) is the reference consumer. It mixes both directives:

- `demo_fragment`, `demo_page`, `demo_oob_primary` — inline-rendered and swap-addressable (`{% block %}`)
- `demo_form` — inline-rendered, also the re-render target on 422 (`{% block %}`)
- `demo_form_ok`, `demo_sse_item`, `demo_mutation_counter` — swap-only (`{% fragment %}`)

Read `app.py` alongside the template to see which routes target which blocks.

## Suspense deferred blocks

**Do not** convert `Suspense` deferred slots to `{% fragment %}`. Suspense works by rendering the **shell** first (with deferred keys set to `None`), then streaming each deferred block as an OOB swap after its awaitable resolves. If the slot were `{% fragment %}`, the shell would render an empty div instead of a skeleton — defeating the "shell-first" UX.

Use a regular `{% block %}` with a loading check:

```kida
{% block stats %}
  {% if stats is not none %}
    <div>{{ stats.users }} users</div>
  {% else %}
    <div class="skeleton"></div>
  {% endif %}
{% endblock %}
```

See the [Suspense documentation](/chirp/docs/streaming/) for the full pattern.

## Migration recipe

Converting a `{% block %}` + `is defined` workaround to `{% fragment %}`:

**Before**

```kida
{% block notification %}
{% if msg is defined %}
<div class="toast">{{ msg }}</div>
{% endif %}
{% endblock %}
```

**After**

```kida
{% fragment notification %}
<div class="toast">{{ msg }}</div>
{% end %}
```

**Steps**

1. Rename `{% block foo %}` → `{% fragment foo %}` and `{% endblock %}` → `{% end %}`.
2. Drop the `{% if ... is defined %}` or `{% if ... %}` truthiness guard that was protecting the block body from full-render exposure.
3. Drop `| default(...)` filters on variables that only exist in the fragment's context.
4. If the block previously rendered a placeholder inline (e.g. `"Counter: 0"`), decide: is an empty swap target acceptable on page load? If yes, convert to `{% fragment %}`. If no, keep `{% block %}` and leave the default filter in place.

Run `rg '{% if .* is defined %}'` afterwards — any remaining hits are either legitimate conditionals (e.g. error display) or missed workarounds. The error-display case is cleaner with `.get(...)`:

```kida
{% if _errors.get("name") %}<span class="err">{{ _errors.get("name") }}</span>{% endif %}
```

## What chirp does for you

- **Block metadata** (`template.block_metadata()`) surfaces fragment blocks identically to regular blocks — no consumer needs to know the difference.
- **`/_frag{path}?_b=name`** dispatcher resolves fragment blocks.
- **Page shell contracts** (`PageShellContract.targets`) accept fragment blocks as required or optional targets.
- **OOB registry** (`app.register_oob_region(...)`) accepts fragment block names.
- **Contract checks**:
  - `check_unreachable_blocks` does **not** flag fragment blocks — they are unreachable from composition roots *by design*.
  - `check_fragment_target_orphans` and `check_page_shell_contracts` walk `block_metadata()` and catch typos in fragment block names the same way.
  - `check_sse_event_crossref` infers targets from literal `Fragment(target=...)` calls and reports mismatches with `sse-swap=...` attributes.

## Reference

- Directive: [kida `{% fragment %}` docs](https://lbliii.github.io/kida/docs/directives/fragment/)
- Related: [OOB Registry & Fail-Loud Rendering](/chirp/docs/guides/oob-registry/), [App Shells](/chirp/docs/guides/app-shell/), [Streaming: Suspense](/chirp/docs/streaming/)
