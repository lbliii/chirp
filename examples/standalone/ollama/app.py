"""Ollama Chat — talk to a local LLM that can call tools.

A chat UI where you talk to llama3.2 running on Ollama. The model has
access to chirp tools (notes, time, calculator) and its tool calls
stream live to an activity panel via SSE. The assistant's response
streams token-by-token for a real-time typing effect.

Uses framework primitives: ``LLM``, ``AgentRun``, and ``InMemoryConversationStore``.

Requires:
    pip install httpx patitas[syntax]   # (or pip install chirp[all])
    ollama pull llama3.2

Run:
    ollama serve        # in one terminal
    python app.py       # in another
"""

import contextvars
import os
import threading
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from chirp import App, AppConfig, EventStream, Fragment, Request, SSEEvent, Template
from chirp.ai import LLM, AgentRun, InMemoryConversationStore
from chirp.ai.errors import AIError, ProviderError
from chirp.ai.events import StreamEvent, StreamToolCallEvent, TokenEvent
from chirp.markdown import register_markdown_filter

TEMPLATES_DIR = Path(__file__).parent / "templates"

OLLAMA_BASE = os.environ.get("OLLAMA_BASE", "http://localhost:11434")
DEFAULT_MODEL = "llama3.2:3b"
_THREAD_ID = "default"

_model: str = DEFAULT_MODEL
_model_lock = threading.Lock()

config = AppConfig(template_dir=TEMPLATES_DIR, worker_mode="async")
app = App(config=config)
register_markdown_filter(app)

_store = InMemoryConversationStore()
_agent: AgentRun | None = None
_agent_model: str | None = None

SYSTEM_PROMPT = (
    "You are a helpful assistant with access to tools. "
    "You can manage notes (add, list, search), tell the current time, "
    "and evaluate math expressions. Use tools when they are relevant "
    "to the user's request. Be concise."
)


def _get_model() -> str:
    with _model_lock:
        return _model


def _set_model(name: str) -> None:
    global _model, _agent, _agent_model
    with _model_lock:
        _model = name
    _agent = None
    _agent_model = None


async def _visible_history() -> list[dict[str, Any]]:
    """User/assistant turns for the chat transcript UI."""
    messages = await _store.load(_THREAD_ID)
    return [
        m
        for m in messages
        if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip()
    ]


def _get_agent() -> AgentRun:
    """Return (and cache) an AgentRun wired to the current Ollama model."""
    global _agent, _agent_model
    app._ensure_frozen()
    registry = app._tool_registry
    assert registry is not None
    model = _get_model()
    if _agent is None or _agent_model != model:
        llm = LLM(f"ollama:{model}")
        _agent = AgentRun(
            llm,
            registry,
            store=_store,
            system=SYSTEM_PROMPT,
            thread_id=_THREAD_ID,
        )
        _agent_model = model
    return _agent


async def _agent_events(
    *, append_user: bool = False, user_message: str = ""
) -> AsyncIterator[StreamEvent]:
    """Yield AgentRun stream events — patch point for tests."""
    agent = _get_agent()
    async for event in agent.stream(user_message, append_user=append_user):
        yield event


async def _collect_agent_reply(
    *, append_user: bool = False, user_message: str = ""
) -> tuple[str, list[str]]:
    """Run the agent loop and return (assistant_text, tool_names)."""
    tools_called: list[str] = []
    parts: list[str] = []
    try:
        async for event in _agent_events(append_user=append_user, user_message=user_message):
            if isinstance(event, StreamToolCallEvent):
                tools_called.append(event.name)
            elif isinstance(event, TokenEvent):
                parts.append(event.text)
    except ProviderError as exc:
        return f"Ollama returned an error: {exc.status}", tools_called
    except httpx.ConnectError:
        return "Could not connect to Ollama. Make sure it's running: `ollama serve`", tools_called
    except AIError as exc:
        return str(exc), tools_called
    except Exception as exc:
        return f"Error: {exc}", tools_called
    return "".join(parts) or "(no response)", tools_called


# ---------------------------------------------------------------------------
# Ollama HTTP client — model listing only (LLM calls use chirp.ai LLM)
# ---------------------------------------------------------------------------

_client_var: contextvars.ContextVar[httpx.AsyncClient | None] = contextvars.ContextVar(
    "ollama_client",
    default=None,
)


@app.on_worker_startup
async def worker_startup() -> None:
    _client_var.set(httpx.AsyncClient(base_url=OLLAMA_BASE, timeout=120.0))


@app.on_worker_shutdown
async def worker_shutdown() -> None:
    client = _client_var.get()
    if client:
        await client.aclose()
        _client_var.set(None)


def _get_client() -> httpx.AsyncClient:
    client = _client_var.get()
    if client is None:
        client = httpx.AsyncClient(base_url=OLLAMA_BASE, timeout=120.0)
        _client_var.set(client)
    return client


async def ollama_list_models(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    response = await client.get("/api/tags")
    response.raise_for_status()
    return response.json().get("models", [])


# ---------------------------------------------------------------------------
# In-memory note storage
# ---------------------------------------------------------------------------

_notes: list[dict[str, Any]] = []
_notes_lock = threading.Lock()
_next_id = 1


@app.tool("add_note", description="Add a note with an optional tag.")
def add_note(text: str, tag: str | None = None) -> dict:
    global _next_id
    with _notes_lock:
        note = {"id": _next_id, "text": text, "tag": tag}
        _next_id += 1
        _notes.append(note)
        return note


@app.tool("list_notes", description="List all saved notes.")
def list_notes() -> list[dict]:
    with _notes_lock:
        return list(_notes)


@app.tool("search_notes", description="Search notes by text substring.")
def search_notes(query: str) -> list[dict]:
    with _notes_lock:
        q = query.lower()
        return [n for n in _notes if q in n["text"].lower()]


@app.tool("get_current_time", description="Get the current date and time.")
def get_current_time() -> str:
    return datetime.now(UTC).strftime("%A, %B %d, %Y at %H:%M:%S UTC")


@app.tool(
    "calculate",
    description="Evaluate a math expression. Supports +, -, *, /, and parentheses.",
)
def calculate(expression: str) -> str:
    allowed = set("0123456789.+-*/() ")
    if not all(c in allowed for c in expression):
        return "Error: only numbers and +, -, *, / operators allowed"
    try:
        result = eval(expression, {"__builtins__": {}}, {})
    except Exception as exc:
        return f"Error: {exc}"
    return str(result)


@app.template_filter("format_args")
def format_args(args: dict) -> str:
    if not args:
        return "\u2014"
    parts = []
    for k, v in args.items():
        parts.append(f'{k}="{v}"' if isinstance(v, str) else f"{k}={v}")
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
async def index():
    history = await _visible_history()
    try:
        client = _get_client()
        raw_models = await ollama_list_models(client)
        model_names = [m["name"] for m in raw_models]
    except Exception:
        model_names = []

    return Template(
        "chat.html",
        history=history,
        model=_get_model(),
        models=model_names,
    )


@app.route("/model", methods=["POST"], name="model.set")
async def set_model(request: Request):
    form = await request.form()
    name = (form.get("model") or "").strip()
    if name:
        _set_model(name)
    return Fragment("chat.html", "model_updated", model=name)


@app.route("/chat", methods=["POST"], name="chat.post")
async def post_chat(request: Request):
    form = await request.form()
    user_message = (form.get("message") or "").strip()
    streaming = form.get("stream") == "1"

    if not user_message:
        return Fragment("chat.html", "empty_response")

    await _store.append(_THREAD_ID, {"role": "user", "content": user_message})

    if streaming:
        return Fragment("chat.html", "stream_start", user_content=user_message)

    return Fragment("chat.html", "chat_pending", user_content=user_message)


@app.route("/chat/complete", name="chat.complete")
async def chat_complete():
    final_content, tools_called = await _collect_agent_reply(append_user=False)
    return Fragment(
        "chat.html",
        "chat_response",
        assistant_content=final_content,
        tools_used=tools_called,
    )


@app.route("/chat/stream", referenced=True)
def chat_stream():
    async def generate():
        tools_called: list[str] = []
        tools_banner_sent = False
        parts: list[str] = []

        try:
            async for event in _agent_events(append_user=False):
                if isinstance(event, StreamToolCallEvent):
                    tools_called.append(event.name)
                elif isinstance(event, TokenEvent):
                    if tools_called and not tools_banner_sent:
                        yield Fragment(
                            "chat.html",
                            "stream_tools_used",
                            target="stream-tools",
                            tools_used=tools_called,
                        )
                        tools_banner_sent = True
                    parts.append(event.text)
                    yield Fragment("chat.html", "stream_token", token=event.text)
        except ProviderError as exc:
            yield Fragment(
                "chat.html",
                "stream_token",
                token=f"Ollama returned an error: {exc.status}",
            )
        except httpx.ConnectError:
            yield Fragment(
                "chat.html",
                "stream_token",
                token="Could not connect to Ollama. Make sure it's running: `ollama serve`",
            )
        except Exception as exc:
            yield Fragment("chat.html", "stream_token", token=f"Error: {exc}")

        yield SSEEvent(event="done", data="complete")

    return EventStream(generate())


@app.route("/feed", referenced=True)
def feed():
    async def generate():
        async for event in app.tool_events.subscribe():
            yield Fragment("chat.html", "activity_row", event=event)

    return EventStream(generate())


@app.route("/clear", methods=["POST"], name="chat.clear")
async def clear():
    global _agent
    await _store.clear(_THREAD_ID)
    _agent = None
    return Fragment("chat.html", "chat_cleared")


if __name__ == "__main__":
    app.run()
