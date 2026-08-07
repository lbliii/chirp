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

## What it is

MCP (Model Context Protocol) lets AI agents call your app's Python functions the
same way htmx calls your routes. Register a function with `@app.tool()` and it
serves two callers from one codebase: your HTTP handlers (which call it directly)
and MCP clients over JSON-RPC.

Reach for this when you want an LLM agent to act on the same data your HTML UI
exposes.

```python
from chirp import App

app = App()

@app.tool("search_inventory", description="Search inventory by keyword")
async def search_inventory(query: str, limit: int = 10) -> list[dict]:
    return await db.search(query, limit=limit)
```

That function is now callable from:

- **Your HTTP handlers** — call it directly, like any other function.
- **MCP clients** — over JSON-RPC at `/mcp`.

:::{note}
The tools and MCP API is provisional. The surface may change between releases.
:::

## Registering tools

Use the `@app.tool()` decorator during setup. The first argument is the tool
name; `description` is sent to MCP clients so agents know what each tool does.

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

Both sync and async handlers work.

Chirp generates JSON Schema from your type annotations, so MCP clients get a
typed parameter list for free. Parameters named `request` are excluded (the same
convention as route handlers).

:::{dropdown} Type-to-schema mapping
The schema is built at freeze time from each parameter's annotation:

- `str` → `"string"`, `int` → `"integer"`, `float` → `"number"`, `bool` → `"boolean"`
- `list[str]` → `"array"` with `"items": {"type": "string"}` (also `list[int]`, `list[float]`)
- `X | None` → optional parameter (unwrapped to `X`, left out of `required`)
- Parameters with a default value are optional
- Parameters named `request` (or annotated `Request`) are excluded
- Unannotated parameters default to `"string"`
:::{/dropdown}

## The MCP endpoint

When at least one tool is registered, Chirp mounts a JSON-RPC endpoint at `/mcp`.
It speaks MCP protocol version `2026-07-28` (stateless core) with the `tools`
capability. There is no handshake or session: each request is independent and
carries protocol version, client identity, and capabilities in
`params._meta`. Optional `server/discover` advertises supported versions;
legacy `initialize` / `notifications/initialized` are accepted as no-ops.

::::{steps}
:::{step} Discover (optional)
Ask the server for supported versions and capabilities.

```bash
curl -X POST http://localhost:8000/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"server/discover","id":1,"params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientInfo":{"name":"curl","version":"1.0"},"io.modelcontextprotocol/clientCapabilities":{}}}}'
```
:::{/step}
:::{step} List tools
Fetch the registered tools and their input schemas. No prior call required.

```bash
curl -X POST http://localhost:8000/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":2,"params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientCapabilities":{}}}}'
```
:::{/step}
:::{step} Call a tool
Dispatch a tool by name with arguments.

```bash
curl -X POST http://localhost:8000/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"tools/call","id":3,"params":{"name":"add_note","arguments":{"text":"Hello"},"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientCapabilities":{}}}}'
```
:::{/step}
::::{/steps}

:::{warning} `/mcp` only exists when a tool is registered
The endpoint is routed only when at least one tool is registered. An app with no
`@app.tool()` calls returns `404` for `/mcp` — that is expected, not a bug. The
path is configurable: `AppConfig(mcp_path="/agent")` moves it.
:::

## Real-time tool activity

Every successful tool call emits a `ToolCallEvent` through `app.tool_events`.
Subscribe from an SSE route to build a live agent-activity dashboard.

```python
from chirp import EventStream, Fragment

@app.route("/activity/feed", referenced=True)
def activity_feed():
    async def stream():
        async for event in app.tool_events.subscribe():
            yield Fragment("dashboard.html", "activity_row", event=event)
    return EventStream(stream())
```

`EventStream` is one of Chirp's [[docs/about/core-concepts/return-values|return types]]; for
the wire format and connection lifecycle see
[[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]].

Each `ToolCallEvent` is a frozen dataclass with:

- `tool_name` — which tool was called
- `arguments` — the arguments passed
- `result` — what it returned
- `timestamp` — when it was called (epoch seconds)
- `call_id` — a unique 12-character hex identifier

Render an event in a template block like any other context value:

```html
{% block activity_row %}
<tr>
  <td><code>{{ event.tool_name }}</code></td>
  <td>{{ event.arguments | format_args }}</td>
  <td>{{ event.call_id[:8] }}</td>
</tr>
{% endblock %}
```

:::{dropdown} Inspecting the registry
After the app is frozen (first request or `app.run()`), `app.tools` returns the
frozen `ToolRegistry`. It is read-only at runtime; accessing it before freeze
raises `RuntimeError`.

```python
for tool_info in app.tools.list_tools():
    print(f"{tool_info['name']}: {tool_info['description']}")

# Look up a specific tool
tool = app.tools.get("add_note")
if tool is not None:
    print(tool.schema)
```
:::{/dropdown}

:::{dropdown} Thread safety
The tools system is built for Python 3.14 free-threading:

- `ToolDef` is a frozen dataclass — immutable, safe to share across threads.
- `ToolRegistry` is built once at freeze time and never mutated.
- `ToolEventBus` guards its subscriber set with a `threading.Lock`.
- Each subscriber gets its own `asyncio.Queue`, so there is no shared mutable
  state on the broadcast path.

For the framework-wide model see
[[docs/about/thread-safety|the free-threading thread-safety model]].
:::{/dropdown}

## Milo MCP Apps registration preview

`chirp.ext.milo` is a provisional, setup-only bridge for applications that
already register commands with Milo 0.4.1. It is separate from the stable
`app.tool()` registry described above: it does not convert either registry,
copy Milo schemas, or expose every Milo command automatically.

The caller attaches `MCPAppToolMeta` when the Milo command is originally
registered, registers the linked `ui://` resource, and opts the canonical
dotted command ID into an exact Chirp allowlist. `adapter.bind()` then records
one existing Chirp template, named block, and parameterless application context
provider. At `app.freeze()`, Chirp verifies the public Milo command/resource
link and publishes frozen binding metadata:

```python
adapter = use_milo(app, cli, allowlist=("work-items.create",))
adapter.bind(
    "work-items.create",
    template="work_items.html",
    block="create_tool",
    context=resource_context,
)

app.freeze()
print(adapter.bindings[0].resource_uri)
```

Milo is already a bounded direct dependency of Chirp, so this preview needs no
additional extra. The adapter never freezes or mutates the caller-owned Milo
CLI, invokes the context provider during freeze, or manufactures a Chirp
request/session. Application state captured by the provider remains
application-owned and must be safe for concurrent reads.

This is registration groundwork, not MCP App HTML rendering. Issue #578 owns
invoking the provider and rendering the named block through Chirp's existing
fail-loud render surface. The offline
[`milo_mcp_apps` example](https://github.com/lbliii/chirp/tree/main/examples/standalone/milo_mcp_apps)
keeps that boundary executable without adding a parallel template or
placeholder HTML path.

## The shipping example

The runnable demo registers three tools, serves a notes UI, and streams tool
calls into a live activity feed. The tool definitions:

```python
@app.tool("add_note", description="Add a note with an optional tag.")
def add_note(text: str, tag: str | None = None) -> dict:
    global _next_id
    with _lock:
        note = {"id": _next_id, "text": text, "tag": tag}
        _next_id += 1
        _notes.append(note)
        return note


@app.tool("list_notes", description="List all notes.")
def list_notes() -> list[dict]:
    with _lock:
        return list(_notes)


@app.tool("search_notes", description="Search notes by text substring.")
def search_notes(query: str) -> list[dict]:
    with _lock:
        q = query.lower()
        return [n for n in _notes if q in n["text"].lower()]
```

*Source: [`examples/standalone/tools/app.py`](https://github.com/lbliii/chirp/blob/main/examples/standalone/tools/app.py).*

Run the full example with `python app.py`, open it in a browser, then call a
tool with `curl` and watch the activity feed update in real time.

## See also

:::{note} See also
- [[docs/about/core-concepts/return-values|Return values]] — every return type, including `EventStream`
- [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]] — SSE patterns for real-time feeds
- [[docs/about/thread-safety|Thread safety]] — the free-threading model the registry relies on
:::
