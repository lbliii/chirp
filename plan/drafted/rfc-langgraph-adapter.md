# RFC: LangGraph adapter — complex agent graphs via EventStream UI

**Status**: Accepted design gate for Phase 3 epic #423 / issue #441. No core implementation scheduled — adapter-only.
**Date**: 2026-06-22
**Scope**: Optional `chirp-langgraph` bridge, examples, streaming UI mapping
**Related**: #420 (AI saga), #423 (Phase 3), #442 (HITL), `plan/drafted/rfc-ai-friendly-chirp.md`

> **North star:** LangGraph owns graph state; Chirp owns **streaming hypermedia** for human-visible steps.

---

## 1. Problem

`AgentRun` covers the common **single-loop tool-use** pattern. Apps with branching graphs, checkpointing, parallel nodes, or LangGraph `Interrupt` semantics outgrow it. Rebuilding StateGraph in core would abandon the integrate-don't-rebuild strategy.

Chirp still needs a **documented seam** so LangGraph apps render into SSE/Fragment UI without a SPA side channel.

---

## 2. Decision summary

| Concern | Owner |
|---------|-------|
| Graph definition, checkpoints, interrupts | **LangGraph** (app or `chirp-langgraph` adapter) |
| Node execution, tool dispatch | LangGraph + existing `chirp.tools` |
| Human-visible streaming | **Chirp** `EventStream` + templates |
| HITL approve/deny UI | Chirp `#442` primitives (web forms), not LangGraph UI widgets |

**Bright line:** No `StateGraph`, checkpointer, or interrupt runtime in `src/chirp/core`.

---

## 3. Adapter shape (sketch)

```python
from langgraph.graph import StateGraph
from chirp_langgraph import graph_to_event_stream

graph = build_support_graph()  # app-owned
compiled = graph.compile(checkpointer=...)

@app.route("/agent/run", methods=["POST"])
async def run_agent(request: Request):
    state = {"messages": [...]}

    async def stream():
        async for lg_event in compiled.astream_events(state, version="v2"):
            fragment = graph_event_to_fragment(lg_event)  # adapter mapping
            if fragment is not None:
                yield fragment

    return EventStream(stream())
```

Adapter responsibilities:

- Map LangGraph event types → `Fragment` / `SSEEvent` (node start/end, tool call, interrupt)
- Optional: map LangGraph `Interrupt` → Chirp `StreamToolApprovalEvent` + session resume (#442)

Adapter non-responsibilities:

- Defining graph topology
- Persisting checkpoints (LangGraph checkpointer)
- Replacing `AgentRun` for simple apps

---

## 4. Event mapping table

| LangGraph / agent event | Chirp UI target |
|-------------------------|-----------------|
| `on_chat_model_stream` | `stream_to_fragments` / response block |
| `on_tool_start` | Activity row (pending), OOB |
| `on_tool_end` | Activity row (complete) |
| `interrupt` (HITL) | Approval fragment (#442) + pause; resume via form POST |
| Graph step boundary | Optional step indicator block |

Same **no JSON side channel** rule: primary UI stays HTML fragments over SSE.

---

## 5. HITL boundary vs LangGraph Interrupt

| | LangGraph Interrupt | Chirp HITL (#442) |
|--|---------------------|-------------------|
| Trigger | Graph node raises interrupt | `@app.tool(approval_required=True)` or agent pause |
| Resume | `Command(resume=...)` into graph | Form POST + `AgentRun.stream(resume_approval_id=...)` |
| Transport | Python API / SDK | **Server-rendered form + CSRF** |
| CSRF / session | App responsibility | First-class via `secure_stack()` patterns |

**Composition:** LangGraph interrupt handler renders Chirp approval Fragment; resume payload feeds back into `graph.invoke(Command(resume=...))`. Chirp does not embed LangGraph's interrupt protocol — it provides web-native gates apps wire up.

---

## 6. Packaging

- `pip install chirp[ai]` — `AgentRun` only
- `pip install chirp-langgraph` (optional) — depends on `langgraph`, maps events to Fragments
- Example: `examples/standalone/langgraph_bridge/` (future, after adapter exists)

---

## 7. Non-goals

- In-core StateGraph / checkpoint store
- Visual graph editor
- LangSmith trace UI clone
- Automatic graph → MCP tool export

---

## 8. Success criteria (#441)

- [x] RFC documents adapter boundary and EventStream mapping
- [ ] Optional package stub or example sketch (implementation deferred)
- [ ] README cross-links HITL (#442) for interrupt resume

---

## 9. When to use what

| App shape | Use |
|-----------|-----|
| Chat + tools + SSE activity | `AgentRun` (core) |
| Retrieval + streamed answer | `stream_with_sources` + optional RAG bridge (#439) |
| Multi-node graph, checkpoints, parallel branches | LangGraph + `chirp-langgraph` adapter |
| Dangerous tool gate | Chirp HITL (#442), composable with either loop |
