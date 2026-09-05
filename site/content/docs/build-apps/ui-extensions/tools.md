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
- `X | Y` → `"anyOf"` with each supported alternative
- `X | None` → optional parameter (unwrapped to `X`, left out of `required`)
- Parameters with a default value are optional
- Parameters named `request` (or annotated `Request`) are excluded
- Unannotated parameters default to `"string"`
:::{/dropdown}

Before invoking a tool, Chirp validates arguments against the `inputSchema`
advertised by `tools/list`. Missing required arguments, incorrect types, and
incorrect array item types return JSON-RPC `-32602` (`Invalid arguments`) with
the tool name, argument path, and expected type or missing-field explanation.
The handler is not entered and values are not coerced. Omit optional arguments
to use their Python defaults; `X | None` currently advertises `X`, so an explicit
JSON `null` does not satisfy that schema.

## The MCP endpoint

When at least one tool is registered, Chirp mounts a JSON-RPC endpoint at `/mcp`.
It speaks MCP protocol version `2026-07-28` (stateless Streamable HTTP core)
with the `tools` capability.

**Stateless transport.** There is no handshake or server-side session. Each
`POST` is independent: protocol version, client identity, and capabilities ride
in per-request `params._meta` (reserved keys under
`io.modelcontextprotocol/…`). Optional `server/discover` advertises supported
versions. Legacy `initialize` / `notifications/initialized` remain
accept-and-noop for older clients — they do not create session state.

**Standard MCP `2025-06-18` clients (Cursor, Claude Code, …).** These clients
negotiate during `initialize` via `params.protocolVersion` and then send
`MCP-Protocol-Version: 2025-06-18` on follow-up requests. Chirp echoes the
requested version, does **not** attach `chirp/legacyOfframp`, and does **not**
require SEP-2243 `Mcp-Method` / `Mcp-Name` routing headers — method and tool
name stay in the JSON-RPC body. This is the path Orrery and most IDE MCP hosts
use today.

**Streamable HTTP routing headers (SEP-2243).** Modern clients that advertise
protocol `2026-07-28` must also send routing headers that agree with the
JSON-RPC body:

| Header | Required when | Must match |
|--------|---------------|------------|
| `MCP-Protocol-Version` | Modern path (see below) | `params._meta` protocol version |
| `Mcp-Method` | Modern path | JSON-RPC `method` |
| `Mcp-Name` | `tools/call` (also `resources/read`, `prompts/get`) | `params.name` (or `params.uri`) |

Enforcement is gated: if **neither** the `MCP-Protocol-Version` header **nor**
`params._meta` protocol version is present — or only the legacy `2024-11-05`
version is advertised — Chirp stays on the legacy offramp path and does not
require these headers. Once either advertises a modern (non-legacy) version,
missing or mismatched headers return **HTTP 400** with JSON-RPC error
`HeaderMismatch` (`-32020`). `Mcp-Name` may use a Base64 sentinel form
`=?base64?<data>?=` when the name is not header-safe.

:::{warning} Legacy `2024-11-05` clients — bridged through 2027-07-28
Handshake-era clients (explicit `2024-11-05`, `initialize` /
`notifications/initialized`, or no protocol-version advertisement) still work:
Chirp bridges them with a `DeprecationWarning` and a structured note on
`initialize` responses. SEP-2243 routing-header enforcement applies only when a
**modern** protocol version is advertised. `app.check()` emits an INFO
`mcp_legacy` issue when tools are registered. Migrate clients to `2026-07-28`
with per-request `_meta` and `MCP-Protocol-Version` / `Mcp-Method` / `Mcp-Name`
before the offramp ends.
:::

::::{steps}
:::{step} Discover (optional)
Ask the server for supported versions and capabilities.

```bash
curl -X POST http://localhost:8000/mcp \
  -H 'Content-Type: application/json' \
  -H 'MCP-Protocol-Version: 2026-07-28' \
  -H 'Mcp-Method: server/discover' \
  -d '{"jsonrpc":"2.0","method":"server/discover","id":1,"params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientInfo":{"name":"curl","version":"1.0"},"io.modelcontextprotocol/clientCapabilities":{}}}}'
```
:::{/step}
:::{step} List tools
Fetch the registered tools and their input schemas. No prior call required.

```bash
curl -X POST http://localhost:8000/mcp \
  -H 'Content-Type: application/json' \
  -H 'MCP-Protocol-Version: 2026-07-28' \
  -H 'Mcp-Method: tools/list' \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":2,"params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientCapabilities":{}}}}'
```
:::{/step}
:::{step} Call a tool
Dispatch a tool by name with arguments. Include `Mcp-Name` for `tools/call`.

```bash
curl -X POST http://localhost:8000/mcp \
  -H 'Content-Type: application/json' \
  -H 'MCP-Protocol-Version: 2026-07-28' \
  -H 'Mcp-Method: tools/call' \
  -H 'Mcp-Name: add_note' \
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
Bridge that bus into an `EventStream` for a live invocation log (or hand-roll
the same pattern with `Fragment` yields).

```python
from chirp.tools import mount_invocation_log, tool_event_stream

# One-liner: SSE route + packaged invocation_row fragment (default /invocations/live)
mount_invocation_log(app)

# Or compose the bridge yourself:
@app.route("/activity/feed", referenced=True)
def activity_feed():
    return tool_event_stream(app.tool_events, template="dashboard.html", block="activity_row")
```

`mount_skills(...)` wires `mount_invocation_log` by default for Orrery-style
hosts; pass `invocation_log_path=None` to skip the live log.

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

## Skill tools with machine scopes

Provisional ``chirp.skill`` mounts signed tool handlers onto the same MCP
registry. Gate a skill tool on machine-token scopes with
``@skill.tool(..., scopes=(...))`` — Chirp calls ``enforce_auth(AuthSpec(scopes=...))``
before the body. Declare each scope with ``app.register_scope`` so the
``auth_spec`` contract can validate names at startup:

```python
from chirp.skill import Skill, use_skill

skill = Skill("hooks", version="1.0.0", private_key=private, key_id="hooks-1")

@skill.tool("dispatch", scopes=("webhook:write",))
def dispatch(payload: dict) -> dict:
    return payload

use_skill(app, skill)
app.register_scope("webhook:write")
```

A caller missing the scope gets a 403 from ``enforce_auth``; the skill wrapper
maps that to ``ToolAuthError`` and MCP ``tools/call`` returns a JSON-RPC error
(``-32603``, message ``Forbidden``) while emitting ``authz.scope.denied``.

## Milo MCP Apps named-block resources

`chirp.ext.milo` is a provisional bridge for applications that already register
commands with Milo 0.4.1. It is separate from the stable `app.tool()` registry
described above: it does not convert either registry, copy Milo schemas, or
expose every Milo command automatically.

The caller attaches `MCPAppToolMeta` when the Milo command is originally
registered, registers the linked `ui://` resource, and opts the canonical
dotted command ID into an exact Chirp allowlist. `adapter.bind()` then records
one existing Chirp template, named block, and parameterless application context
provider. At `app.freeze()`, Chirp verifies the public Milo command/resource
link and publishes frozen binding metadata. On each MCP App resource read, the
caller-owned `@cli.ui_resource` handler delegates to
`adapter.render_resource(operation_id)`, which invokes the context provider and
renders that named block through `Fragment` / `App.render`:

```python
@cli.ui_resource("ui://chirp/work-items/create", name="Create work item")
def create_work_item_resource() -> str:
    return adapter.render_resource("work-items.create")

adapter = use_milo(app, cli, allowlist=("work-items.create",))
adapter.bind(
    "work-items.create",
    template="work_items.html",
    block="create_tool",
    context=resource_context,
)

app.freeze()
print(adapter.bindings[0].resource_uri)
print(adapter.render_resource("work-items.create"))
```

Milo is already a bounded direct dependency of Chirp, so this preview needs no
additional extra. The adapter never freezes or mutates the caller-owned Milo
CLI, invokes the context provider during freeze, or manufactures a Chirp
request/session. Application state captured by the provider remains
application-owned and must be safe for concurrent reads. Missing blocks raise
`BlockNotFoundError`; empty required UI output and non-mapping context raise
`ConfigurationError`. Host CSP/sandbox/auth semantics for the read-only
resource profile remain with issue #579.

The offline
[`milo_mcp_apps` example](https://github.com/lbliii/chirp/tree/main/examples/standalone/milo_mcp_apps)
proves browser page, htmx fragment, MCP tool structured result, and negotiated
MCP App resource HTML from one template contract.

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
