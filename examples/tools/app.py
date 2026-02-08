"""MCP Tools — the simplest chirp app with tool support.

Registers Python functions as MCP tools that AI agents can discover
and call via JSON-RPC at ``/mcp``. The same functions are also
available to normal route handlers.

Run:
    python app.py

Try with curl:
    # Initialize MCP session
    curl -X POST http://localhost:8000/mcp -H 'Content-Type: application/json' \
        -d '{"jsonrpc":"2.0","method":"initialize","id":1,"params":{}}'

    # List available tools
    curl -X POST http://localhost:8000/mcp -H 'Content-Type: application/json' \
        -d '{"jsonrpc":"2.0","method":"tools/list","id":2,"params":{}}'

    # Add a note
    curl -X POST http://localhost:8000/mcp -H 'Content-Type: application/json' \
        -d '{"jsonrpc":"2.0","method":"tools/call","id":3,"params":{"name":"add_note","arguments":{"text":"Buy milk","tag":"errands"}}}'

    # List all notes
    curl -X POST http://localhost:8000/mcp -H 'Content-Type: application/json' \
        -d '{"jsonrpc":"2.0","method":"tools/call","id":4,"params":{"name":"list_notes","arguments":{}}}'

    # Search notes
    curl -X POST http://localhost:8000/mcp -H 'Content-Type: application/json' \
        -d '{"jsonrpc":"2.0","method":"tools/call","id":5,"params":{"name":"search_notes","arguments":{"query":"milk"}}}'
"""

import threading

from chirp import App

app = App()

# ---------------------------------------------------------------------------
# In-memory storage — thread-safe for free-threading
# ---------------------------------------------------------------------------

_notes: list[dict] = []
_lock = threading.Lock()
_next_id = 1


# ---------------------------------------------------------------------------
# Tools — callable by MCP clients and route handlers alike
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
# Routes — humans interact here, tools power the data
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    return {"notes": list_notes(), "tool_count": 3}


if __name__ == "__main__":
    app.run()
