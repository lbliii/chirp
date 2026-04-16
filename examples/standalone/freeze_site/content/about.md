---
title: About This Site
order: 10
category: Meta
description: How this demo site works.
---

# About This Site

A demonstration of **Chirp freeze** — the same app serves live pages with htmx
navigation *and* produces static HTML via `chirp freeze`.

## How It Works

1. Markdown files in `content/` are parsed at startup by `DocsPlugin`
2. Routes return `Page()` — full page for browsers, fragment for htmx
3. Layout composition wraps every page in `_layout.html`
4. Alpine.js is injected automatically by middleware
5. `chirp freeze` walks the route table and renders each URL
6. Parameterized routes expand via `freeze_params`
7. URLs are rewritten to relative paths so output works on any static host

The frozen output is identical to what the live server produces — minus
absolute URLs, which are rewritten to relative paths for static hosting.
