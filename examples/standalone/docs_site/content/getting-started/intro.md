---
title: Introduction
order: 1
category: Getting Started
description: Learn what this app does and how it works.
---
# Introduction

This example app demonstrates `chirp.docs` — a module that serves
hand-written markdown alongside auto-generated API reference, all
from a single `DocsPlugin` mount.

## Features

- Browse hand-written guides under **Getting Started** and **Guides**
- Auto-generated route and tool reference under **API Reference**
- Full-text search via the sidebar input
- Fragment navigation (htmx) for instant page swaps
- MCP tools (`search_docs`, `get_doc`, `list_docs`) for AI agents

## Quick Start

```python
from chirp import App
from chirp.docs import DocsPlugin

app = App()
app.mount("/docs", DocsPlugin(content_dir="content"))
app.run()
```
