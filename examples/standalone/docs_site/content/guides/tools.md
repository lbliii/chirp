---
title: MCP Tools
order: 1
category: Guides
description: Expose functionality to AI agents via @tool.
---
# MCP Tools

Chirp apps expose tools to AI agents via the MCP protocol:

```python
@app.tool("echo", description="Echo back the input")
def echo(message: str) -> str:
    return message
```

## How It Works

1. Register tools with `@app.tool(name, description=)`
2. At freeze, Chirp generates JSON Schema from function signatures
3. Tools serve via the `/mcp` endpoint using JSON-RPC

## Docs Plugin Tools

When `DocsPlugin(tools=True)`, three tools are registered automatically:

| Tool | Description |
|------|-------------|
| `search_docs(query)` | Keyword search across all pages |
| `get_doc(slug)` | Retrieve a specific page by slug |
| `list_docs(category?)` | List pages, optionally by category |

These return raw markdown — useful for LLM consumption.

## Try It

```bash
curl -X POST http://localhost:8000/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"search_docs","arguments":{"query":"contacts"}}}'
```
