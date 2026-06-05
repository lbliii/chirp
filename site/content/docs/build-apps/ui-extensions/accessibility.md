---
title: Accessibility
description: Semantic markup, ARIA, and WCAG alignment for inclusive Chirp apps
draft: false
weight: 10
lang: en
type: doc
tags: [accessibility, aria, wcag, semantic]
keywords: [accessibility, aria, wcag, semantic, screen-reader]
category: guide
---

## Overview

Chirp apps serve HTML over the wire. Following accessibility best practices ensures your app works for users of assistive technologies (screen readers, keyboard navigation) and benefits all users.

This guide covers patterns aligned with [WCAG](https://www.w3.org/WAI/WCAG21/quickref/) (Web Content Accessibility Guidelines). For comprehensive guidance, see the [WAI-ARIA Authoring Practices](https://www.w3.org/WAI/ARIA/apg/) and [MDN Accessibility](https://developer.mozilla.org/en-US/docs/Web/Accessibility).

## Static Accessibility Checks

Accessibility is a contract, not a convention. Chirp scans your templates at startup and in CI as part of `app.check()` and reports accessibility regressions before they ship. Five checks run, all at `WARNING` severity:

| Category | Catches |
|---|---|
| `a11y_interactive` | htmx URL attributes (`hx-get`/`hx-post`/`hx-put`/`hx-patch`/`hx-delete`) on non-interactive elements that lack `role` and `tabindex` — use `<button>`/`<a>`, or add `role="button" tabindex="0"`. |
| `a11y_label` | Form fields (`<input>`/`<select>`/`<textarea>`) with no associated label — no matching `<label for="…">`, no wrapping `<label>`, and no `aria-label`/`aria-labelledby`. Hidden, submit, button, and reset inputs are exempt. |
| `a11y_alt` | `<img>` tags with no `alt` attribute. Use `alt="…"` for meaningful images and `alt=""` for decorative ones. |
| `a11y_heading` | Heading levels that skip (for example `<h1>` straight to `<h3>` with no `<h2>`), which breaks the document outline for screen readers. |
| `a11y_landmark` | Layout templates with no `<main>` (or `role="main"`) landmark. Only layouts are checked, since pages inherit their landmark structure from the layout. |

These run automatically wherever `app.check()` runs — at startup in debug mode and in CI via `chirp check myapp:app`. The contract message names the offending template and the concrete fix. See the [[docs/quality/contracts-debugging/categories|Contract Category Reference]] for the full category list.

### Strict accessibility posture

The five checks are `WARNING` by default so they do not block apps mid-migration. If you want accessibility regressions to fail the build, promote individual categories to `ERROR` using the existing severity-override mechanism — no new API:

```python
from chirp.contracts.types import Severity

app.override_contract_severity("a11y_label", Severity.ERROR)
app.override_contract_severity("a11y_alt", Severity.ERROR)
```

Now an unlabeled form field or an image without `alt` text fails `app.check()` outright. Combine with `chirp check myapp:app --warnings-as-errors` if you instead want every warning category to fail in CI.

## Semantic HTML

Use elements that convey meaning:

- `header`, `main`, `nav`, `footer` for page structure
- `article`, `section` for content grouping
- `h1`–`h6` for headings (in order, no skips)
- `button` for actions, `a` for navigation
- `label` for form controls
- `ul`/`ol`/`li` for lists

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

## ARIA for Dynamic Content

When content updates via htmx or SSE, use ARIA to announce changes:

- `aria-live="polite"` — announces updates without interrupting
- `aria-atomic="true"` — reads the entire region when it changes
- `aria-label` — describes regions and controls

The RAG demo uses this pattern for streaming answers:

```html
<div sse-swap="answer" hx-target="this" aria-live="polite" aria-atomic="true">
  <span class="thinking">Searching docs and generating answer…</span>
</div>
```

## Forms

- Associate `label` with inputs via `for`/`id` or wrap the input
- Use `aria-describedby` for validation messages
- Use `aria-invalid` when a field has errors
- Provide `aria-label` for icon-only buttons

```html
<label for="question-input">Your question</label>
<textarea id="question-input" name="question" aria-describedby="validation"></textarea>
<div id="validation" role="alert" aria-live="polite"></div>
```

## Images and Media

- Always provide `alt` for images (empty string `alt=""` for decorative images)
- Use `title` or `aria-label` for icon buttons

## Keyboard and Focus

- Ensure all interactive elements are focusable and operable via keyboard
- Use visible focus styles (avoid `outline: none` without a replacement)
- For custom controls (e.g. switches), use `role="switch"` and `aria-checked`

## Next Steps

- [[docs/build-apps/html-fragments/filters|Filters]] — Security filters and escaping
- [[docs/examples/rag-demo|RAG demo]] — Example with ARIA and semantic structure
- [WCAG Quick Reference](https://www.w3.org/WAI/WCAG21/quickref/) — Full guidelines
