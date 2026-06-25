---
title: Document Catalog Protocol
description: DCP v3 — the format-agnostic catalog graph interchange for agents and external tools.
weight: 45
section: about
tags:
  - agents
  - architecture
---

# Document Catalog Protocol (DCP)

Chirp Docs indexes prose into a **live catalog graph** and exports it as
`catalog.json`. The Document Catalog Protocol (DCP) describes that export:
nodes, typed edges, normalized Content IR, and agent indexes — without requiring
consumers to parse markdown.

## Three tiers

| Tier | What | Required? |
|------|------|-----------|
| **Catalog graph** | Nodes, edges, namespaces, search metadata | Yes |
| **Content IR** | Headings, links, extensions (semantic summary) | Recommended |
| **Native AST** | Format-specific sidecar for incremental diff | Optional |

`content_format` is an open string (`patitas-markdown`, `html`, `docutils-rst`, …).
Markdown is the canonical authoring dialect; other formats are migration bridges.

## HTTP surfaces

| Endpoint | Purpose |
|----------|---------|
| `GET /catalog.json` | Full federated graph (DCP v3) |
| `GET /catalog/retrieve?id=` | Page + chunks + backlinks + similar |
| `GET /search/semantic?q=` | Hybrid keyword + semantic search |
| `GET /objects.inv` | Reference inventory for external clients |
| `GET /tools.json` | Agent tool discovery |

## Validation

Exports are validated against a JSON Schema at freeze and in
`chirp docs check --content-only`:

```bash
chirp docs check --content-only
chirp docs freeze --full
```

The schema ships with the runtime (`catalog/schemas/catalog-v3.schema.json`).
See the in-repo spec: [DCP.md](https://github.com/lbliii/chirp/blob/main/examples/chirp_docs/DCP.md)
in `examples/chirp_docs/`.

## For standalone consumers

You do not need to run the hypermedia app to consume DCP:

1. Fetch `catalog.json` or per-mount shards from a frozen export
2. Validate against the v3 schema
3. Use `content` blocks and `structure.json` for agent queries

The graph is the protocol. Markdown is source.
