"""Ollama Chat — talk to a local LLM that can call tools.

A chat UI where you talk to llama3.2 running on Ollama. The model has
access to chirp tools (notes, time, calculator) and its tool calls
stream live to an activity panel via SSE.

Requires:
    pip install httpx   # (or pip install chirp[all])
    ollama pull llama3.2

Run:
    ollama serve        # in one terminal
    python app.py       # in another
"""

import contextvars
import json as json_module
import threading
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from chirp import App, AppConfig, EventStream, Fragment, Request, Template
from chirp.tools.registry import ToolRegistry

TEMPLATES_DIR = Path(__file__).parent / "templates"

OLLAMA_BASE = "http://localhost:11434"
MODEL = "llama3.2"

config = AppConfig(template_dir=TEMPLATES_DIR)
app = App(config=config)


# ---------------------------------------------------------------------------
# Ollama HTTP client helpers
# ---------------------------------------------------------------------------


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
        result = eval(expression, {"__builtins__": {}}, {})  # noqa: S307
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


@app.template_filter("format_time")
def format_time(ts: float) -> str:
    """Format a unix timestamp as HH:MM:SS."""
    return datetime.fromtimestamp(ts, UTC).strftime("%H:%M:%S")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    """Full page — chat UI and activity panel."""
    with _history_lock:
        history = list(_history)
    return Template("chat.html", history=history)


@app.route("/chat", methods=["POST"])
async def post_chat(request: Request):
    """Run the agent loop and stream the response via SSE."""
    form = await request.form()
    user_message = (form.get("message") or "").strip()
    if not user_message:
        return Fragment("chat.html", "empty_response")

    # Record user message in history
    _append_history("user", user_message)

    async def generate():
        # Yield the user message bubble first
        yield Fragment("chat.html", "user_bubble", content=user_message)

        client = _get_client()

        # Ensure the app is frozen so the tool registry is compiled
        app._ensure_frozen()
        registry = app._tool_registry
        assert registry is not None

        ollama_tools = chirp_tools_to_ollama(registry)

        # Build messages: system prompt + full history
        with _history_lock:
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": SYSTEM_PROMPT},
            ]
            messages.extend(_history)

        # --- Agent loop: non-streaming tool rounds ---
        max_rounds = 10
        for _ in range(max_rounds):
            response = await ollama_chat(
                client,
                model=MODEL,
                messages=messages,
                tools=ollama_tools,
            )

            msg = response.get("message", {})
            tool_calls = msg.get("tool_calls")

            if not tool_calls:
                # Final answer — send it to the browser
                final_content = msg.get("content", "") or "(no response)"
                yield Fragment("chat.html", "assistant_token", token=final_content)
                _append_history("assistant", final_content)
                break

            # Append the assistant message with tool_calls to the loop messages
            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": msg.get("content", ""),
                "tool_calls": tool_calls,
            }
            messages.append(assistant_msg)

            # Dispatch each tool call through the registry (fires event bus)
            for call in tool_calls:
                func = call.get("function", {})
                tool_name = func.get("name", "")
                tool_args = func.get("arguments", {})

                # Status fragment so the user sees what's happening
                yield Fragment(
                    "chat.html",
                    "tool_status",
                    tool_name=tool_name,
                    tool_args=tool_args,
                )

                try:
                    result = await registry.call_tool(tool_name, tool_args)
                    result_str = (
                        json_module.dumps(result, default=str)
                        if isinstance(result, dict | list)
                        else str(result)
                    )
                except Exception as exc:
                    result_str = f"Error: {exc}"

                # Append tool result for the next Ollama round
                messages.append({"role": "tool", "content": result_str})

    return EventStream(generate())


@app.route("/feed")
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
