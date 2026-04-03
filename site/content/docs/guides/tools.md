---
title: Tools & MCP
description: Register Python functions as MCP tools for AI agents alongside HTTP routes
draft: false
weight: 50
lang: en
type: doc
tags: [tools, mcp, ai, agents]
keywords: [tools, mcp, ai, agents, json-rpc, tool-call, event-bus]
category: guide
---

## The Idea

Humans interact with your app through HTML forms and htmx. AI agents interact through the same functions via MCP (Model Context Protocol). One codebase, two interfaces.

```python
from chirp import App

app = App()

@app.tool("search_inventory", description="Search inventory by keyword")
async def search_inventory(query: str, limit: int = 10) -> list[dict]:
    return await db.search(query, limit=limit)
```

This function is now callable from:
- **HTTP routes** (call it directly in your handlers)
- **MCP clients** via JSON-RPC at `/mcp`

## Registering Tools

Use the `@app.tool()` decorator during setup:

```python
@app.tool("add_note", description="Add a note with an optional tag.")
def add_note(text: str, tag: str | None = None) -> dict:
    note = {"id": next_id(), "text": text, "tag": tag}
    store.append(note)
    return note

@app.tool("list_notes", description="List all notes.")
def list_notes() -> list[dict]:
    return list(store)
```

Both sync and async handlers work. The `description` is sent to MCP clients so agents understand what each tool does.

### Schema Generation

Chirp auto-generates JSON Schema from your function's type annotations:

- `str` -> `"string"`, `int` -> `"integer"`, `float` -> `"number"`, `bool` -> `"boolean"`
- `list[str]` -> `"array"` with `"items": {"type": "string"}`
- `X | None` -> optional parameter (not in `required`)
- Parameters with defaults are optional
- Parameters named `request` are excluded (same convention as route handlers)

## The MCP Endpoint

Chirp automatically mounts a JSON-RPC endpoint at `/mcp`. It speaks the MCP v1 protocol:

```bash
# Initialize handshake
curl -X POST http://localhost:8000/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"initialize","id":1,"params":{}}'

# List available tools
curl -X POST http://localhost:8000/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":2,"params":{}}'

# Call a tool
curl -X POST http://localhost:8000/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"tools/call","id":3,"params":{"name":"add_note","arguments":{"text":"Hello"}}}'
```

## Inspecting Registered Tools

After the app is frozen (first request or `app.run()`), inspect the registry:

```python
for tool_info in app.tools.list_tools():
    print(f"{tool_info['name']}: {tool_info['description']}")

# Look up a specific tool
tool = app.tools.get("add_note")
if tool is not None:
    print(tool.schema)
```

The `app.tools` property returns the frozen `ToolRegistry`. It's read-only at runtime.

## Real-Time Tool Activity

Every tool call emits a `ToolCallEvent` through `app.tool_events`. Subscribe from an SSE route to build live dashboards:

```python
from chirp import EventStream, Fragment

@app.route("/activity/feed", referenced=True)
def activity_feed():
    async def stream():
        async for event in app.tool_events.subscribe():
            yield Fragment("dashboard.html", "activity_row", event=event)
    return EventStream(stream())
```

Each `ToolCallEvent` is a frozen dataclass with:
- `tool_name` -- which tool was called
- `arguments` -- the arguments passed
- `result` -- what it returned
- `timestamp` -- when it was called
- `call_id` -- unique 12-char hex identifier

### Template for Activity Rows

```html
{% block activity_row %}
<tr>
  <td><code>{{ event.tool_name }}</code></td>
  <td>{{ event.arguments | format_args }}</td>
  <td>{{ event.call_id[:8] }}</td>
</tr>
{% endblock %}
```

## Thread Safety

The tools system is designed for Python 3.14 free-threading:

- `ToolDef` is a frozen dataclass (immutable, safe to share)
- `ToolRegistry` is built once at freeze time, never mutated
- `ToolEventBus` uses a `threading.Lock` to protect subscriber queues
- Each subscriber gets its own `asyncio.Queue` (no shared mutable state)

## Next Steps

- See the **tools example** (`examples/standalone/tools/`) for a complete working app
- [[docs/core-concepts/return-values|Return Values]] -- All return types including EventStream
- [[docs/streaming/server-sent-events|Server-Sent Events]] -- SSE patterns for real-time feeds
