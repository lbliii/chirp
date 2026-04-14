---
title: Search
order: 3
category: Guides
description: Full-text search across documentation.
---
# Search

The docs index includes a search input in the sidebar. It uses htmx
to fetch results as you type — no page reload, no JavaScript framework.

## How It Works

The search input sends a debounced `GET /docs/search?q=...` request.
The server returns a `Fragment` with matching results, which htmx swaps
into the main content area.

Results are ranked by relevance: title matches are weighted 3x over
body matches. Search covers both hand-written and autodoc pages.

## AI Agent Search

Agents search via the `search_docs` MCP tool:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_docs",
    "arguments": {"query": "contacts"}
  }
}
```

This returns raw markdown content with slug, title, source, and category.
