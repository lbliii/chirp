"""Tool HITL — human approval before dangerous agent tool calls."""

from __future__ import annotations

import os
import threading
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from chirp import App, AppConfig, EventStream, Fragment, Request, Template
from chirp.ai import AgentRun, InMemoryConversationStore
from chirp.ai._tool_calls import ChatCompletion
from chirp.ai.events import (
    DoneEvent,
    StreamEvent,
    StreamToolApprovalEvent,
    TokenEvent,
)
from chirp.middleware.csrf import CSRFConfig, CSRFMiddleware, csrf_field
from chirp.middleware.sessions import SessionConfig, SessionMiddleware
from chirp.tools import InMemoryToolApprovalStore

TEMPLATES_DIR = Path(__file__).parent / "templates"
_THREAD_ID = "default"

_notes: list[dict[str, Any]] = []
_lock = threading.Lock()
_next_id = 1

config = AppConfig(template_dir=TEMPLATES_DIR, worker_mode="async")
app = App(config=config)
_secret = os.environ.get("SESSION_SECRET_KEY", "dev-only-not-for-production")
app.add_middleware(SessionMiddleware(SessionConfig(secret_key=_secret)))
app.add_middleware(CSRFMiddleware(CSRFConfig()))
app.template_global("csrf_field")(csrf_field)

_store = InMemoryConversationStore()
_approval_store = InMemoryToolApprovalStore()


class _DemoLLM:
    """Deterministic LLM stub — requests ``delete_all_notes`` once, then answers."""

    provider = "openai"

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Any = None,
        system: str | None = None,
    ) -> ChatCompletion:
        has_tool_result = any(m.get("role") == "tool" for m in messages)
        if not has_tool_result:
            return ChatCompletion(
                content="",
                tool_calls=(
                    {
                        "call_id": "call_delete",
                        "name": "delete_all_notes",
                        "arguments": {},
                    },
                ),
                assistant_message={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_delete",
                            "type": "function",
                            "function": {
                                "name": "delete_all_notes",
                                "arguments": "{}",
                            },
                        }
                    ],
                },
            )
        return ChatCompletion(
            content="",
            tool_calls=(),
            assistant_message={"role": "assistant", "content": ""},
        )

    async def stream_events(
        self,
        messages: list[dict[str, Any]],
        *,
        system: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        if any(m.get("role") == "tool" for m in messages):
            yield TokenEvent(text="All notes cleared.")
        yield DoneEvent()


_demo_llm = _DemoLLM()


def _approval_store_for_agent() -> InMemoryToolApprovalStore:
    """Process-local store — fine for single-worker demos and tests."""
    return _approval_store


def _get_agent(*, approval_store: Any) -> AgentRun:
    app._ensure_frozen()
    registry = app._tool_registry
    assert registry is not None
    return AgentRun(
        _demo_llm,
        registry,
        store=_store,
        approval_store=approval_store,
        thread_id=_THREAD_ID,
    )


async def _events_to_fragments(events: AsyncIterator[StreamEvent]) -> AsyncIterator[Fragment]:
    async for event in events:
        if isinstance(event, StreamToolApprovalEvent):
            yield Fragment(
                "notes.html",
                "approval_dialog",
                approval_id=event.approval_id,
                tool_name=event.name,
                arguments=event.arguments,
            )
        elif isinstance(event, TokenEvent):
            yield Fragment("notes.html", "agent_reply", text=event.text)
        elif isinstance(event, DoneEvent):
            yield Fragment("notes.html", "note_list", notes=list_notes())


@app.tool("add_note", description="Add a note.")
def add_note(text: str) -> dict[str, Any]:
    global _next_id
    with _lock:
        note = {"id": _next_id, "text": text}
        _next_id += 1
        _notes.append(note)
        return note


@app.tool("list_notes", description="List all notes.")
def list_notes() -> list[dict[str, Any]]:
    with _lock:
        return list(_notes)


@app.tool(
    "delete_all_notes",
    description="Delete every note — destructive.",
    approval_required=True,
)
def delete_all_notes() -> dict[str, int]:
    global _next_id
    with _lock:
        count = len(_notes)
        _notes.clear()
        _next_id = 1
        return {"deleted": count}


@app.template_filter("format_args")
def format_args(args: dict[str, Any]) -> str:
    if not args:
        return "—"
    return ", ".join(f"{k}={v!r}" for k, v in args.items())


@app.route("/")
def index() -> Template:
    return Template("notes.html", notes=list_notes())


@app.route("/notes", methods=["POST"], name="notes.add")
async def post_note(request: Request) -> Fragment:
    form = await request.form()
    text = (form.get("text") or "").strip()
    if text:
        add_note(text)
    return Fragment("notes.html", "note_list", notes=list_notes())


@app.route("/agent/run", methods=["POST"], name="agent.run")
async def run_agent() -> Fragment:
    await _store.clear(_THREAD_ID)
    return Fragment("notes.html", "agent_panel")


@app.route("/agent/stream", referenced=True)
async def agent_stream() -> EventStream:
    approval_store = _approval_store_for_agent()
    agent = _get_agent(approval_store=approval_store)

    async def generate() -> AsyncIterator[Fragment]:
        async for fragment in _events_to_fragments(agent.stream("Clear all notes please")):
            yield fragment

    return EventStream(generate())


@app.route("/agent/resume", methods=["POST"], name="agent.resume")
async def resume_agent(request: Request) -> Fragment:
    from chirp.middleware.sessions import get_session

    form = await request.form()
    session = get_session()
    session["agent_resume"] = {
        "approval_id": (form.get("approval_id") or "").strip(),
        "decision": (form.get("decision") or "").strip(),
    }
    return Fragment("notes.html", "agent_panel", stream_url="/agent/resume/stream")


@app.route("/agent/resume/stream", referenced=True)
async def resume_stream(request: Request) -> EventStream:
    from chirp.middleware.sessions import get_session

    session = get_session()
    payload = session.pop("agent_resume", {}) or {}
    approval_id = (request.query.get("approval_id") or payload.get("approval_id") or "").strip()
    decision = (request.query.get("decision") or payload.get("decision") or "").strip()
    approval_store = _approval_store_for_agent()

    if decision == "approve":
        await approval_store.mark_approved(approval_id)
    elif decision == "deny":
        await approval_store.mark_denied(approval_id)

    agent = _get_agent(approval_store=approval_store)

    async def generate() -> AsyncIterator[Fragment]:
        async for fragment in _events_to_fragments(
            agent.stream("", append_user=False, resume_approval_id=approval_id)
        ):
            yield fragment

    return EventStream(generate())


if __name__ == "__main__":
    app.run()
