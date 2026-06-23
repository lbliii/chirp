# RFC: AI-friendly Chirp — architecture, API shapes, and stability criteria

**Status**: Draft — accepted as the Phase 1 design gate for saga #420 / epic #421. Implementation tracked in child issues #425–#444.
**Date**: 2026-06-22
**Scope**: `src/chirp/ai/`, `src/chirp/tools/`, `src/chirp/app/`, examples (`ollama`, `tools`, `llm_playground`), `docs/public-api.md`
**Related**: #420 (saga), #421–#423 (phase epics), #339 (Universal handler), #344 (Contract diff), `plan/drafted/epic-agent-vibe-dx.md` (historical agent-DX — separate concern)

> **North star:** The agent loop, tool registry, and streaming HTML are **one system** — not three libraries glued together in example code.

---

## 1. Problem

Chirp already leads on **LLM streaming → live HTML** (`EventStream` + `Fragment` is the moat). The 2026-06-22 feature-maturity parity audit (Chirp vs FastAPI, Django, LangGraph, PydanticAI, LlamaIndex) shows the remaining gap is the **cognitive runtime**: tool loops, MCP client, memory, tracing, and a stable public contract.

Today that runtime is **example-owned**:

| Concern | Where it lives today | Gap |
|---------|---------------------|-----|
| Tool registration + MCP server | `app.tool()`, `ToolRegistry`, `handle_mcp_request()` | Server surface exists; **no MCP client**, auth-middleware integration tests thin |
| LLM access | `chirp.ai.LLM` (`generate`, `stream`, structured dataclass mode) | **Not top-level stable**; no `stream_events()`; no native tool-use API |
| Agent loop | Hand-rolled in `examples/standalone/ollama/app.py` (`_run_tool_rounds`) | **~150 lines per app**; provider-specific (Ollama JSON shape) |
| Activity UI | `ToolEventBus` + `EventStream(app.tool_events.subscribe())` | Works; not scaffolded |
| Conversation memory | Global `_history` list in ollama example | **No framework abstraction** |
| Observability | None on LLM/tool paths | OTel spans missing; ContextVar loss in SSE generators (#429) |
| Stability | `ToolRegistry` provisional; `LLM` subpackage-only | `docs/public-api.md` lines 89–90 — tools "young compared with core hypermedia" |

An AI-native framework should not require every app author to reimplement `_run_tool_rounds`, re-encode Ollama vs OpenAI tool-call shapes, and wire SSE dashboards by hand.

---

## 2. Design principles (bright lines)

All Phase 1–3 work must respect these — they are non-negotiable:

1. **No per-client server view state.** Conversation history is keyed by session/tenant, not held in handler closures.
2. **No WebSocket return type.** SSE + `Fragment` / `EventStream` / `signal()` remain the primary LLM→UI transport.
3. **Contracts over conventions.** AI surfaces must be checkable (`app.check()`) and test-covered before promotion to stable.
4. **Chirp owns UI transport + secure tool hosting; integrate don't rebuild.** Vector RAG → optional plugin (LlamaIndex bridge). Complex agent graphs → optional LangGraph adapter. No in-core vector store, no StateGraph clone, no LangSmith clone.
5. **MCP server runs through middleware.** Auth, CSRF, rate limits apply to `/mcp` the same as HTML routes — already true for `handle_mcp_request(request, registry)`.
6. **Free-threading safety.** Immutable registries at freeze time; per-request httpx clients; no shared mutable LLM state.

---

## 3. Current state (as-built audit)

### 3.1 `chirp.ai` — thin LLM streaming

```python
from chirp.ai import LLM, stream_to_fragments, stream_with_sources

llm = LLm("anthropic:claude-sonnet-4-20250514")
text = await llm.generate("...")
async for token in llm.stream("..."):
    ...
summary = await llm.generate(Summary, prompt="...")  # frozen dataclass
```

| Piece | Location | Notes |
|-------|----------|-------|
| Providers | `_providers.py` | anthropic, openai, ollama, lmstudio, localai |
| Structured output | `_structured.py` | dataclass → JSON schema; parse with retry left to #436 |
| Streaming helpers | `streaming.py` | `stream_to_fragments`, `stream_with_sources` (RAG-shaped) |
| Errors | `errors.py` | `AIError`, `ProviderError`, `StructuredOutputError` |
| Extra | `pip install chirp[ai]` | httpx required |

**Not yet built:** `stream_events()`, native tool-use on `LLM`, provider adapters for Gemini/Bedrock/Azure (#444).

### 3.2 `chirp.tools` — MCP server + event bus

```python
@app.tool("search", description="Search inventory")
async def search(query: str) -> list[dict]:
    return await db.search(query)

# MCP JSON-RPC at POST /mcp (middleware pipeline)
# Live dashboard:
async for event in app.tool_events.subscribe():
    yield Fragment("dashboard.html", "row", event=event)
```

| Piece | Location | Notes |
|-------|----------|-------|
| Registry | `registry.py` | `ToolDef`, `ToolRegistry`, `compile_tools()` at freeze |
| MCP handler | `handler.py` | initialize, tools/list, tools/call; protocol `2024-11-05` |
| Events | `events.py` | `ToolCallEvent`, `ToolEventBus` (thread-safe broadcast) |
| Schema | `schema.py` | `function_to_schema()` from type hints |

**Not yet built:** MCP **client** (#434), remote toolset merge into registry.

### 3.3 Reference agent loop (example-owned)

`examples/standalone/ollama/app.py` is the canonical **anti-pattern we want to replace**:

- `_prepare_agent()` — freeze app, get registry, convert schemas to Ollama format
- `_run_tool_rounds()` — up to 10 non-streaming rounds, dispatch via `registry.call_tool()`
- Separate streaming path for final token delivery
- Global `_history` + locks for demo memory

This pattern proves the hypermedia UI (chat + activity SSE) but belongs in **`chirp.ai` or `chirp.tools`**, not copied per example.

### 3.4 Examples map

| Example | Teaches | Target after Phase 2 |
|---------|---------|----------------------|
| `standalone/tools` | MCP server + activity SSE | Keep; add README MCP+SSE pattern (#456) |
| `standalone/ollama` | Hand-rolled agent loop | Refactor to framework primitives (#438) |
| `chirpui/llm_playground` | Streaming LLM in shell | Keep; core tests mock LLM (#426) |
| *(planned)* `llm_minimal` | Zero-Ollama streaming demo | #454 |
| *(planned)* `chirp new --ai` | Scaffold chat+tools+SSE | #437 |

---

## 4. Target API (Phase 1 → Phase 3)

### 4.1 Stable surface goal (#430)

Promote to **stable** in `chirp.__all__` + `docs/public-api.md`:

| Name | Module | Phase |
|------|--------|-------|
| `LLM` | `chirp.ai` | 1 (after #426 tests + #427 spans) |
| `stream_to_fragments`, `stream_with_sources` | `chirp.ai.streaming` | 1 |
| `AIError`, `ProviderError`, `StructuredOutputError` | `chirp.ai.errors` | 1 |
| `ToolRegistry`, `ToolDef`, `ToolCallEvent`, `ToolEventBus` | `chirp.tools` | 1 (after #425 ✅, middleware auth test optional) |
| `stream_events()` | `chirp.ai` | 2 (#431) |
| `AgentRun` (or `run_agent()`) | `chirp.ai` or `chirp.tools` | 2 (#433) |
| `ConversationStore` protocol + session impl | `chirp.ai.memory` | 2 (#435) |
| MCP client types | `chirp.tools.client` | 2 (#434) |

**Provisional until Phase 1 closes:** everything above stays provisional in `public-api.md` until the stability bar (§7) is met.

### 4.2 `LLM` — extensions

Current API stays; add:

```python
# Phase 2 — unified event stream (#431)
async for event in llm.stream_events(prompt, tools=registry):
    match event:
        case TokenEvent(text=token):
            ...
        case ToolCallEvent(name=name, arguments=args, call_id=id):
            ...
        case ToolResultEvent(call_id=id, result=result):
            ...
        case ErrorEvent(error=err):
            ...
        case DoneEvent():
            ...
```

```python
# Phase 2 — native tool-use (#432)
response = await llm.generate(
    prompt,
    tools=app.tools,          # ToolRegistry or list[ToolDef]
    tool_choice="auto",       # provider-mapped
)
# Returns structured message with optional tool_calls; provider adapters
# translate OpenAI / Anthropic / Ollama shapes internally.
```

Structured output hardening (#436): retry with repair prompt on `StructuredOutputError`; optional Pydantic alongside dataclass.

### 4.3 `AgentRun` — framework-owned tool loop (#433)

Replace `_run_tool_rounds` with:

```python
from chirp.ai import AgentRun  # name TBD — see open questions

run = AgentRun(
    llm=llm,
    tools=app.tools,
    store=session_store,       # optional ConversationStore
    max_rounds=10,
)

async for event in run.stream(user_message):
    # Same StreamEvent union as llm.stream_events()
    # + dispatches tools via ToolRegistry.call_tool()
    # + emits ToolCallEvent on bus automatically
    ...
```

**Responsibilities:**
- Multi-round tool loop until model stops calling tools
- Append assistant/tool messages to `ConversationStore`
- Emit on `ToolEventBus` (reuse existing event type)
- Yield `stream_events()` union for UI binding

**Non-responsibilities:** RAG retrieval, human-in-the-loop approval (#442), graph branching (LangGraph #441).

### 4.4 `ConversationStore` (#435)

```python
class ConversationStore(Protocol):
    async def load(self, key: str) -> list[Message]: ...
    async def append(self, key: str, message: Message) -> None: ...
    async def clear(self, key: str) -> None: ...
```

| Implementation | Scope | Notes |
|----------------|-------|-------|
| `SessionConversationStore` | Phase 2 | Key = session id; uses existing session middleware |
| `DatabaseConversationStore` | Phase 2+ | Optional; app-owned schema |
| In-memory global list | **Rejected** | ollama example pattern; not production-safe |

Messages are **provider-neutral dicts** (role, content, tool_calls, tool_call_id) — adapters translate at the LLM boundary.

### 4.5 MCP client (#434)

```python
from chirp.tools.client import MCPClient

remote = MCPClient("https://other-service/mcp", auth=...)
await remote.connect()
merged = app.tools.merge(remote.tools())  # or compile-time registry extension
```

Client consumes remote `tools/list`, registers as namespaced tools (`remote__search`), proxies `tools/call`. Runs through same auth story as outbound httpx.

**Phase 2 scope:** single remote server, stdio transport deferred.

---

## 5. Event model

### 5.1 `StreamEvent` union (canonical)

All streaming paths (`LLM.stream_events`, `AgentRun.stream`, SSE adapters) share one tagged union:

| Variant | Fields | UI mapping |
|---------|--------|------------|
| `TokenEvent` | `text: str` | Append to response block via `stream_to_fragments` |
| `ToolCallEvent` | `name, arguments, call_id` | Activity panel row (pending) |
| `ToolResultEvent` | `call_id, result, error?` | Activity panel row (complete) |
| `ErrorEvent` | `error: AIError` | Error block / toast |
| `DoneEvent` | `usage?: TokenUsage` | Finalize; enable submit button |

Implement as frozen dataclasses + `typing.Protocol` or `@dataclass` tagged union — **not** a deep class hierarchy.

### 5.2 UI transport (unchanged moat)

```
StreamEvent*  →  adapter  →  Fragment / SSEEvent  →  htmx sse-swap
```

Adapters (existing + new):

| Adapter | Input | Output |
|---------|-------|--------|
| `stream_to_fragments` | `AsyncIterator[str]` | `Fragment` per token |
| `stream_events_to_fragments` *(new)* | `AsyncIterator[StreamEvent]` | token → response block; tool events → OOB activity rows |
| `tool_events.subscribe()` | `ToolCallEvent` | activity dashboard (existing) |

**No JSON side channel for primary UI.** Structured data for islands uses existing `Fragment` context or narrow `JSONResponse` islands — not a parallel chat API.

---

## 6. Observability (#427, #428, #429)

| Span | Attributes | Phase |
|------|------------|-------|
| `llm.generate` | provider, model, prompt_tokens, completion_tokens | 1 |
| `llm.stream` | provider, model, (token count on DoneEvent) | 1 |
| `tool.call` | tool_name, duration_ms, error | 1 |
| SSE generator | Propagate OTel context into `EventStream` async generators | 1 (#429) |

Pattern: wrap provider HTTP calls and `ToolRegistry.call_tool()` — mirror existing middleware OTel hooks. **Fail-open:** tracing absence must not break streaming.

---

## 7. Stability bar (promotion checklist — #430)

An AI surface moves from **provisional → stable** when **all** rows pass:

| Gate | Proof |
|------|-------|
| **Core unit tests** | No live API keys; httpx mock transport (#426 LLM, #425 MCP ✅) |
| **Example smoke** | At least one example uses the surface without hand-rolled loop |
| **OTel spans** | LLM + tool.call spans emitted (#427, #428) |
| **Public API docs** | `docs/public-api.md` + `chirp.__all__` + stability map in `chirp.__init__` |
| **Contract category** *(optional Phase 1)* | e.g. `ai_tools_registered` INFO when `@app.tool` without description |
| **Changelog fragment** | User-visible promotion note |
| **RFC alignment** | No undocumented public names |

**Explicitly not required for 1.0 stable:** MCP client, AgentRun, ConversationStore, RAG plugin — those ship provisional in Phase 2–3.

---

## 8. Non-goals

| Non-goal | Reason |
|----------|--------|
| In-core vector store / embeddings | Optional plugin (#439, #440); integrate LlamaIndex |
| LangGraph / StateGraph in core | Optional adapter (#441) |
| LangSmith-style trace UI | OTel export is enough; no built-in trace browser |
| WebSocket chat transport | SSE + Fragment bet |
| JSON REST chat API as primary surface | Hypermedia-first; narrow islands OK |
| Auto OpenAPI from tools | MCP is the machine surface |
| Built-in prompt registry / eval harness in core | `chirp eval` helpers optional (#443) |
| Multi-agent orchestration | Out of scope; apps compose explicitly |

---

## 9. Integration: Universal handler (#339)

Horizon RFC #339 proposes one handler → HTTP, htmx, MCP, CLI. **This RFC is compatible but not blocked on it.**

| Today | After #339 |
|-------|------------|
| `@app.route` + `@app.tool` registered separately | `@surface` / composed decorators register all surfaces |
| Tool handler ≠ route handler (usually) | Same function when intent matches |
| MCP returns JSON text blocks | Same template block rendered to text/HTML |

**Phase 2 seam:** `AgentRun` should accept tools from `app.tools` regardless of whether tools were registered via `@app.tool` or universal handler — registry is the integration point.

**Contract diff (#344)** should include MCP tool schema changes when `#339` lands; defer `surface_parity` category until universal handler is drafted.

---

## 10. Phase map (implementation order)

### Phase 1 — Trustworthy AI surface (#421)

| Issue | Deliverable | Depends on |
|-------|-------------|------------|
| **#424** | **This RFC** | — |
| #425 | MCP handler core tests | ✅ closed |
| #426 | LLM provider unit tests | RFC |
| #427 | OTel spans: LLM | RFC |
| #428 | OTel spans: tool.call | RFC |
| #429 | OTel ContextVar fix in SSE | #427 |
| #430 | Promote tools/MCP/LLM to stable | #426–#429 |

### Phase 2 — Complete the AI loop (#422)

| Issue | Deliverable |
|-------|-------------|
| #431 | `stream_events()` |
| #432 | Native tool-use API |
| #433 | `AgentRun` / framework tool loop |
| #434 | MCP client |
| #435 | `ConversationStore` |
| #436 | Structured output hardening |
| #437 | `chirp new --ai` scaffold |
| #438 | Refactor ollama example |

### Phase 3 — Optional depth (#423)

#439–#444 — RAG RFC, vector plugin, LangGraph adapter, HITL UI, eval helpers, extra providers.

---

## 11. Open questions (need resolution in Phase 1)

| # | Question | Options | Recommendation |
|---|----------|---------|----------------|
| 1 | `AgentRun` vs module-level `run_agent()` | class / function | **Class** — holds llm+tools+store config; `.stream()` method |
| 2 | Top-level `from chirp import LLM`? | subpackage-only / top-level | **Top-level lazy import** when promoting #430 (match `ToolRegistry`) |
| 3 | MCP auth rejection test location | core / example integration | **Core** — TestClient through middleware stack (follow-up to #425) |
| 4 | `StreamEvent` module path | `chirp.ai.events` / `chirp.ai.streaming` | **`chirp.ai.events`** — keeps streaming.py as adapters only |
| 5 | Provider tool-call shape ownership | per-provider in `_providers` / shared normal form | **Shared normal form** in `chirp.ai._tool_calls`; adapters at boundary |

---

## 12. Acceptance (closes #424)

- [x] RFC in `plan/drafted/rfc-ai-friendly-chirp.md`
- [x] Target API, event model, stability bar, non-goals documented
- [x] Reviewed against parity audit gaps (tool loop, MCP client, tracing, memory)
- [x] Universal handler (#339) integration seam described
- [x] Phase 1–3 issue map linked

**Next implementation issue:** #426 (LLM provider unit tests) — can start immediately in parallel with #427/#428.
