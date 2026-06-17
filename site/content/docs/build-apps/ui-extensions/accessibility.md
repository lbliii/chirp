---
title: Accessibility
description: The five startup/CI accessibility contract checks Chirp runs, and the semantic-HTML and ARIA patterns it expects
draft: false
weight: 10
lang: en
type: doc
tags: [accessibility, aria, wcag, semantic]
keywords: [accessibility, aria, wcag, semantic, screen-reader]
category: guide
---

## Overview

Accessibility in Chirp is a contract, not a convention. `app.check()` scans your templates at startup and in CI, and fails loud on five common regressions: htmx handlers on non-interactive elements, unlabeled form fields, images missing `alt`, skipped heading levels, and layouts with no `<main>` landmark.

This page shows what each check catches, how to promote it to a hard build failure, and the semantic-HTML and ARIA patterns Chirp expects you to ship. If you arrived here from a contract warning, the [accessibility checks](#accessibility-contract-checks) below name your fix.

## Accessibility contract checks

Five checks run wherever [[docs/quality/contracts-debugging/_index|`app.check()` validates contracts]] — at startup in debug mode, and in CI via `chirp check myapp:app`. The contract message names the offending template and the concrete fix. All five emit at `WARNING` severity, so they surface regressions without blocking an app mid-migration.

:::{list-table}
:header-rows: 1

* - Category
  - Catches
  - Fix
* - `a11y_interactive`
  - htmx URL attributes (`hx-get`/`hx-post`/`hx-put`/`hx-patch`/`hx-delete`) on non-interactive elements.
  - Use `<button>` or `<a>`, or add `role="button" tabindex="0"`.
* - `a11y_label`
  - `<input>`/`<select>`/`<textarea>` with no associated label — no matching `<label for="…">`, no wrapping `<label>`, no `aria-label`/`aria-labelledby`. Hidden, submit, button, and reset inputs are exempt.
  - Add `<label for="id">`, wrap the field in a `<label>`, or set `aria-label`.
* - `a11y_alt`
  - `<img>` tags with no `alt` attribute.
  - Use `alt="…"` for meaningful images, `alt=""` for decorative ones.
* - `a11y_heading`
  - Heading levels that skip — for example `<h1>` straight to `<h3>` with no `<h2>` — which breaks the document outline for screen readers.
  - Use heading levels in order with no gaps.
* - `a11y_landmark`
  - Layout templates with no `<main>` (or `role="main"`) landmark. Only layouts are checked; pages inherit landmark structure from the layout.
  - Add `<main>` or `role="main"` to the layout.
:::

:::{tip} Fail the build on accessibility regressions
The five checks are `WARNING` by default. To make a regression fail `app.check()` outright, [[docs/quality/contracts-debugging/categories|promote a category to ERROR]] with `override_contract_severity`:

```python
from chirp import Severity

app.override_contract_severity("a11y_label", Severity.ERROR)
app.override_contract_severity("a11y_alt", Severity.ERROR)
```

An unlabeled form field or an image without `alt` text now fails the check. To instead fail in CI on *every* warning category, run `chirp check myapp:app --warnings-as-errors` — see how to [[docs/quality/contracts-debugging/route-contract|gate CI on warnings]].
:::

## Semantic HTML

The checks reward semantic markup: elements that convey meaning give screen readers a structure to navigate, and they keep `a11y_heading` and `a11y_landmark` quiet for free.

- `header`, `main`, `nav`, `footer` for page structure
- `article`, `section` for content grouping
- `h1`–`h6` for headings, in order, no skips
- `button` for actions, `a` for navigation
- `label` for form controls

```html
<header>
  <nav aria-label="Main navigation">...</nav>
</header>
<main>
  <article aria-label="Question and answer">
    <h2>Question</h2>
    <p>...</p>
  </article>
</main>
```

## ARIA for dynamic content

When content updates via htmx or SSE, ARIA announces the change to assistive technology:

- `aria-live="polite"` — announces updates without interrupting
- `aria-atomic="true"` — reads the entire region when it changes
- `aria-label` — describes regions and controls

The [[docs/examples/rag-demo|RAG demo]] uses this pattern for the streaming answer region:

```html
      <div sse-swap="answer" hx-target="this" aria-live="polite" aria-atomic="true">
        <span class="chirpui-text-muted">Searching docs and generating answer…</span>
        {{ typing_indicator() }}
      </div>
```

*Source: [`examples/chirpui/rag_demo/templates/ask.html`](https://github.com/lbliii/chirp/blob/main/examples/chirpui/rag_demo/templates/ask.html).*

## Forms

- Associate `label` with inputs via `for`/`id`, or wrap the input
- Use `aria-describedby` for validation messages
- Use `aria-invalid` when a field has errors
- Provide `aria-label` for icon-only buttons

```html
<label for="question-input">Your question</label>
<textarea id="question-input" name="question" aria-describedby="validation"></textarea>
<div id="validation" role="alert" aria-live="polite"></div>
```

## Images and keyboard

- Always provide `alt` for images — empty string `alt=""` for decorative ones
- Use `aria-label` or `title` for icon-only buttons
- Keep every interactive element focusable and operable by keyboard
- Use visible focus styles; never set `outline: none` without a replacement
- For custom controls (such as switches), use `role="switch"` with `aria-checked`

:::{note} See also
- [[docs/quality/contracts-debugging/categories|Contract category reference]] — every check category and its severity
- [[docs/examples/rag-demo|RAG demo]] — semantic structure and ARIA in working code
- [[docs/build-apps/html-fragments/filters|Filters]] — escaping and security in templates
- [WCAG Quick Reference](https://www.w3.org/WAI/WCAG21/quickref/) — the full guidelines
- [WAI-ARIA Authoring Practices](https://www.w3.org/WAI/ARIA/apg/) — patterns for ARIA roles and widgets
- [MDN Accessibility](https://developer.mozilla.org/en-US/docs/Web/Accessibility) — reference for semantic HTML and ARIA
:::
