"""MCP Tools — humans use forms, AI agents use /mcp.

Registers Python functions as MCP tools alongside normal HTTP routes.
Open the app in a browser to see notes and a live activity feed.
When an MCP client calls tools, activity appears in real-time via SSE.

Run:
    python app.py

Try the MCP endpoint with curl:
    # List available tools
    curl -X POST http://localhost:8000/mcp -H 'Content-Type: application/json' \
        -d '{"jsonrpc":"2.0","method":"tools/list","id":1,"params":{}}'

    # Add a note (watch it appear in the browser's activity feed!)
    curl -X POST http://localhost:8000/mcp -H 'Content-Type: application/json' \
        -d '{"jsonrpc":"2.0","method":"tools/call","id":2,"params":{"name":"add_note","arguments":{"text":"Hello from an agent!","tag":"mcp"}}}'
"""

import threading
from pathlib import Path

from chirp import App, AppConfig, EventStream, Fragment, Request, Template

TEMPLATES_DIR = Path(__file__).parent / "templates"

config = AppConfig(template_dir=TEMPLATES_DIR)
app = App(config=config)

# ---------------------------------------------------------------------------
# In-memory storage — thread-safe for free-threading
# ---------------------------------------------------------------------------

_notes: list[dict] = []
_lock = threading.Lock()
_next_id = 1


# ---------------------------------------------------------------------------
# Tools — callable by MCP clients AND by route handlers
# ---------------------------------------------------------------------------


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
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    """Full page — notes list and activity feed."""
    return Template("notes.html", notes=list_notes())


@app.route("/notes", methods=["POST"])
async def post_note(request: Request):
    """Add a note via form submission — returns the notes list fragment."""
    form = await request.form()
    text = (form.get("text") or "").strip()
    tag = (form.get("tag") or "").strip() or None
    if text:
        add_note(text, tag=tag)
    return Fragment("notes.html", "note_list", notes=list_notes())


@app.route("/feed", referenced=True)
def feed():
    """Stream tool call events via SSE for the live activity feed."""

    async def generate():
        async for event in app.tool_events.subscribe():
            yield Fragment("notes.html", "activity_row", event=event)

    return EventStream(generate())


if __name__ == "__main__":
    app.run()
