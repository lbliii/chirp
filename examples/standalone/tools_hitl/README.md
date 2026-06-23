# Tool HITL example

Human-in-the-loop approval for dangerous agent tool calls.

## What it shows

- `@app.tool(..., approval_required=True)` on a destructive tool
- `AgentRun` pauses with `StreamToolApprovalEvent` until a human decides
- `InMemoryToolApprovalStore` for the demo (use `SessionToolApprovalStore` in multi-user production)
- CSRF-protected approve/deny forms (same pattern as production apps)
- SSE fragments for approval dialog and resumed agent output

## Run

```bash
python app.py
```

1. Add a few notes.
2. Click **Ask agent to clear all notes**.
3. Approve or deny the `delete_all_notes` tool call in the dialog.

## LangGraph Interrupt boundary

| LangGraph | Chirp HITL |
|-----------|------------|
| Graph node raises `Interrupt` | Tool has `approval_required=True` |
| Resume via `Command(resume=...)` | Form POST → `AgentRun.stream(resume_approval_id=...)` |
| SDK / Python callback UI | Server-rendered Fragment + CSRF |

Chirp does **not** embed LangGraph's interrupt protocol. Apps compose both:
render Chirp approval fragments when a graph interrupts, then feed the
resume payload back into LangGraph. See `plan/drafted/rfc-langgraph-adapter.md`.

## Related

- Issue #442 — HITL tool-approval UI primitives
- `examples/standalone/tools` — MCP tools without approval
- `examples/standalone/ollama` — full agent loop with streaming chat
