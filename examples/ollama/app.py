"""Ollama Chat — talk to a local LLM that can call tools.

A chat UI where you talk to llama3.2 running on Ollama. The model has
access to chirp tools (notes, time, calculator) and its tool calls
stream live to an activity panel via SSE. The assistant's response
streams token-by-token for a real-time typing effect.

Requires:
    pip install httpx   # (or pip install chirp[all])
    ollama pull llama3.2

Run:
    ollama serve        # in one terminal
    python app.py       # in another
"""

import contextvars
import json as json_module
import os
import threading
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from chirp import App, AppConfig, EventStream, Fragment, Request, SSEEvent, Template
from chirp.markdown import register_markdown_filter
from chirp.tools.registry import ToolRegistry

TEMPLATES_DIR = Path(__file__).parent / "templates"

OLLAMA_BASE = os.environ.get("OLLAMA_BASE", "http://localhost:11434")
DEFAULT_MODEL = "llama3.2:3b"

# Current model — global, thread-safe (single-user demo)
_model: str = DEFAULT_MODEL
_model_lock = threading.Lock()

config = AppConfig(template_dir=TEMPLATES_DIR)
app = App(config=config)
register_markdown_filter(app)


def _get_model() -> str:
    with _model_lock:
        return _model


def _set_model(name: str) -> None:
    global _model
    with _model_lock:
        _model = name


# ---------------------------------------------------------------------------
# Ollama HTTP client helpers
# ---------------------------------------------------------------------------


async def ollama_list_models(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    """Fetch locally available models from Ollama."""
    response = await client.get("/api/tags")
    response.raise_for_status()
    return response.json().get("models", [])


def chirp_tools_to_ollama(registry: ToolRegistry) -> list[dict[str, Any]]:
    """Convert chirp MCP tool schemas to Ollama function-calling format.

    MCP:    ``{name, description, inputSchema: {type, properties, required}}``
    Ollama: ``{type: "function", function: {name, description, parameters: ...}}``
    """
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["inputSchema"],
            },
        }
        for t in registry.list_tools()
    ]


async def ollama_chat(
    client: httpx.AsyncClient,
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Send a non-streaming chat request to Ollama.

    Used for tool-calling rounds where we need the complete response
    (including ``tool_calls``) before dispatching.
    """
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools

    response = await client.post("/api/chat", json=payload)
    response.raise_for_status()
    return response.json()


async def ollama_chat_stream(
    client: httpx.AsyncClient,
    *,
    model: str,
    messages: list[dict[str, Any]],
) -> AsyncIterator[str]:
    """Stream a chat response from Ollama, yielding content tokens.

    Ollama streams newline-delimited JSON. Each chunk has a ``message``
    with partial ``content``. We yield each non-empty content fragment.
    If Ollama reports an error mid-stream, it is yielded as text so the
    caller can display it gracefully.
    """
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
    }

    async with client.stream("POST", "/api/chat", json=payload) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line.strip():
                continue
            chunk = json_module.loads(line)
            if "error" in chunk:
                yield f"\n\nOllama error: {chunk['error']}"
                return
            token = chunk.get("message", {}).get("content", "")
            if token:
                yield token


# ---------------------------------------------------------------------------
# Per-worker httpx client (free-threading safe)
# ---------------------------------------------------------------------------

_client_var: contextvars.ContextVar[httpx.AsyncClient | None] = contextvars.ContextVar(
    "ollama_client",
    default=None,
)


@app.on_worker_startup
async def worker_startup() -> None:
    """Create an httpx client for this worker's event loop."""
    _client_var.set(httpx.AsyncClient(base_url=OLLAMA_BASE, timeout=120.0))


@app.on_worker_shutdown
async def worker_shutdown() -> None:
    """Close the httpx client for this worker."""
    client = _client_var.get()
    if client:
        await client.aclose()
        _client_var.set(None)


def _get_client() -> httpx.AsyncClient:
    """Return the per-worker httpx client, creating a fallback if needed."""
    client = _client_var.get()
    if client is None:
        # Fallback for single-worker dev server (no pounce worker hooks)
        client = httpx.AsyncClient(base_url=OLLAMA_BASE, timeout=120.0)
        _client_var.set(client)
    return client


# ---------------------------------------------------------------------------
# Conversation history — global, thread-safe (single-user demo)
# ---------------------------------------------------------------------------

_history: list[dict[str, Any]] = []
_history_lock = threading.Lock()

SYSTEM_PROMPT = (
    "You are a helpful assistant with access to tools. "
    "You can manage notes (add, list, search), tell the current time, "
    "and evaluate math expressions. Use tools when they are relevant "
    "to the user's request. Be concise."
)


def _append_history(role: str, content: str, **extra: Any) -> None:
    """Append a message to conversation history."""
    msg: dict[str, Any] = {"role": role, "content": content}
    msg.update(extra)
    with _history_lock:
        _history.append(msg)


def _clear_history() -> None:
    """Reset conversation history."""
    with _history_lock:
        _history.clear()


# ---------------------------------------------------------------------------
# In-memory note storage — thread-safe
# ---------------------------------------------------------------------------

_notes: list[dict[str, Any]] = []
_notes_lock = threading.Lock()
_next_id = 1

# ---------------------------------------------------------------------------
# Tools — callable by Ollama, MCP clients, and route handlers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Template filters
# ---------------------------------------------------------------------------


@app.template_filter("format_args")
def format_args(args: dict) -> str:
    """Format tool call arguments for display."""
    if not args:
        return "\u2014"
    parts = []
    for k, v in args.items():
        parts.append(f'{k}="{v}"' if isinstance(v, str) else f"{k}={v}")
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Shared: prepare registry + tools for the agent loop
# ---------------------------------------------------------------------------


def _prepare_agent() -> tuple[ToolRegistry, list[dict[str, Any]]]:
    """Freeze the app and return (registry, ollama_tools)."""
    app._ensure_frozen()
    registry = app._tool_registry
    assert registry is not None
    return registry, chirp_tools_to_ollama(registry)


async def _run_tool_rounds(
    client: httpx.AsyncClient,
    messages: list[dict[str, Any]],
    registry: ToolRegistry,
    ollama_tools: list[dict[str, Any]],
    *,
    on_tool_call: Any = None,
    consume_final: bool = True,
) -> str | None:
    """Execute non-streaming tool-calling rounds.

    When ``consume_final`` is True (default), returns the model's final
    content string once it stops calling tools.

    When ``consume_final`` is False the final text response is discarded
    and ``None`` is returned.  The caller should then stream the answer
    separately via :func:`ollama_chat_stream` — this is what enables
    real token-by-token delivery in the streaming path.
    """
    max_rounds = 10
    for _ in range(max_rounds):
        response = await ollama_chat(
            client,
            model=_get_model(),
            messages=messages,
            tools=ollama_tools,
        )

        msg = response.get("message", {})
        tool_calls = msg.get("tool_calls")

        if not tool_calls:
            if consume_final:
                return msg.get("content", "") or "(no response)"
            return None

        # Append the assistant message with tool_calls
        messages.append({
            "role": "assistant",
            "content": msg.get("content", ""),
            "tool_calls": tool_calls,
        })

        # Dispatch each tool call through the registry (fires event bus)
        for call in tool_calls:
            func = call.get("function", {})
            tool_name = func.get("name", "")
            tool_args = func.get("arguments", {})

            if on_tool_call:
                on_tool_call(tool_name, tool_args)

            try:
                result = await registry.call_tool(tool_name, tool_args)
                result_str = (
                    json_module.dumps(result, default=str)
                    if isinstance(result, dict | list)
                    else str(result)
                )
            except Exception as exc:
                result_str = f"Error: {exc}"

            messages.append({"role": "tool", "content": result_str})

    return "(max tool rounds reached)" if consume_final else None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
async def index():
    """Full page — chat UI and activity panel."""
    with _history_lock:
        history = list(_history)

    # Fetch available models for the selector
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


@app.route("/model", methods=["POST"])
async def set_model(request: Request):
    """Switch the active model."""
    form = await request.form()
    name = (form.get("model") or "").strip()
    if name:
        _set_model(name)
    return Fragment("chat.html", "model_updated", model=name)


@app.route("/chat", methods=["POST"])
async def post_chat(request: Request):
    """Handle a chat message.

    When streaming is enabled (default), returns scaffolding HTML that
    opens an SSE connection to ``/chat/stream`` for token-by-token
    delivery. When streaming is off, runs the full agent loop and
    returns the complete response in one fragment.
    """
    form = await request.form()
    user_message = (form.get("message") or "").strip()
    streaming = form.get("stream") == "1"

    if not user_message:
        return Fragment("chat.html", "empty_response")

    _append_history("user", user_message)

    if streaming:
        # Return scaffolding: user bubble + empty assistant bubble
        # that connects to /chat/stream via SSE
        return Fragment("chat.html", "stream_start", user_content=user_message)

    # --- Non-streaming path: full agent loop, return complete response ---
    client = _get_client()
    registry, ollama_tools = _prepare_agent()

    with _history_lock:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]
        messages.extend(_history)

    tools_called: list[str] = []

    try:
        final_content = await _run_tool_rounds(
            client,
            messages,
            registry,
            ollama_tools,
            on_tool_call=lambda name, _args: tools_called.append(name),
        )
        final_content = final_content or "(no response)"
    except httpx.ConnectError:
        final_content = (
            "Could not connect to Ollama. "
            "Make sure it's running: `ollama serve`"
        )
    except httpx.HTTPStatusError as exc:
        final_content = f"Ollama returned an error: {exc.response.status_code}"
    except Exception as exc:
        final_content = f"Error: {exc}"

    _append_history("assistant", final_content)

    return Fragment(
        "chat.html",
        "chat_response",
        user_content=user_message,
        assistant_content=final_content,
        tools_used=tools_called,
    )


@app.route("/chat/stream", referenced=True)
def chat_stream():
    """SSE endpoint: run the agent loop and stream the final answer.

    Tool-calling rounds use non-streaming requests (with ``tools``) so
    we can detect and dispatch tool calls reliably.  Once all tools are
    resolved, a **separate** streaming call (without ``tools``) delivers
    the final answer token-by-token.  Omitting ``tools`` from the
    streaming call prevents the model from emitting raw tool-call JSON
    as text.

    A ``done`` event closes the SSE connection via ``sse-close``.
    """

    async def generate():
        client = _get_client()
        registry, ollama_tools = _prepare_agent()

        with _history_lock:
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": SYSTEM_PROMPT},
            ]
            messages.extend(_history)

        try:
            # --- Phase 1: non-streaming tool rounds ---
            # consume_final=False discards the probe response so we can
            # re-ask with streaming enabled for true token-by-token UX.
            await _run_tool_rounds(
                client,
                messages,
                registry,
                ollama_tools,
                on_tool_call=lambda name, args: None,  # activity panel handles display
                consume_final=False,
            )

            # --- Phase 2: stream the final answer token-by-token ---
            # No tools parameter — model can only respond with text.
            collected: list[str] = []
            async for token in ollama_chat_stream(
                client, model=_get_model(), messages=messages
            ):
                collected.append(token)
                yield Fragment("chat.html", "stream_token", token=token)

            full_response = "".join(collected) or "(no response)"
            _append_history("assistant", full_response)

        except httpx.ConnectError:
            yield Fragment(
                "chat.html",
                "stream_token",
                token=(
                    "Could not connect to Ollama. "
                    "Make sure it's running: `ollama serve`"
                ),
            )
        except Exception as exc:
            yield Fragment("chat.html", "stream_token", token=f"Error: {exc}")

        # Signal the browser to close the SSE connection (sse-close="done")
        yield SSEEvent(event="done", data="complete")

    return EventStream(generate())


@app.route("/feed", referenced=True)
def feed():
    """Stream tool call events via SSE for the live activity panel."""

    async def generate():
        async for event in app.tool_events.subscribe():
            yield Fragment("chat.html", "activity_row", event=event)

    return EventStream(generate())


@app.route("/clear", methods=["POST"])
def clear():
    """Reset conversation history."""
    _clear_history()
    return Fragment("chat.html", "chat_cleared")


if __name__ == "__main__":
    app.run()
