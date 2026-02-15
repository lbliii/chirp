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

- [[docs/templates/filters|Filters]] — Security filters and escaping
- [[docs/examples/rag-demo|RAG demo]] — Example with ARIA and semantic structure
- [WCAG Quick Reference](https://www.w3.org/WAI/WCAG21/quickref/) — Full guidelines
