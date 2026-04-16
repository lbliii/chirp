---
title: Why Hypermedia?
order: 1
category: Articles
description: The case for returning HTML instead of JSON.
tags: [htmx, architecture]
---

# Why Hypermedia?

Hypermedia is the original architecture of the web. Instead of shipping a JSON
API and a JavaScript framework, let the server return HTML and let the browser
do what it was built to do.

This is not a step backward — it is a return to the web's strengths: links,
forms, progressive enhancement, and the stateless request-response cycle.

## The Problem with SPAs

Single-page applications moved rendering to the client. That bought
interactivity but introduced:

- **Bundle size** — hundreds of kilobytes of JavaScript before the first paint
- **State duplication** — the same data modeled on both server and client
- **API churn** — every UI change requires a matching API change

## The Hypermedia Alternative

With htmx, the server sends HTML fragments. The browser swaps them into the
DOM. No client-side router, no state management library, no build step.

```html
<button hx-get="/contacts" hx-target="#list">
  Load Contacts
</button>
```

One attribute. The server returns `<ul>...</ul>`. Done.
