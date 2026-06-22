"""Docs Site — demonstrate chirp.docs with autodoc, search, and MCP tools.

A minimal app with hand-written guides and auto-generated API reference,
all served from a single DocsPlugin mount.

Run:
    uv run python examples/standalone/docs_site/app.py

Browse:
    http://localhost:8000/docs/          — docs index with search
    http://localhost:8000/docs/intro     — hand-written guide
    http://localhost:8000/docs/api/routes/contacts  — autodoc route page
    http://localhost:8000/docs/api/tools/search-docs  — autodoc tool page

MCP:
    curl -X POST http://localhost:8000/mcp \\
      -H 'Content-Type: application/json' \\
      -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"search_docs","arguments":{"query":"contacts"}}}'
"""

from pathlib import Path

from chirp import App, AppConfig, Request
from chirp.docs import DocsPlugin

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
CONTENT_DIR = BASE_DIR / "content"

app = App(AppConfig(template_dir=TEMPLATES_DIR))

# ── Routes ──────────────────────────────────────────────────────────────


@app.route("/")
def index():
    """Home page — redirects to docs."""
    return 'Welcome! Visit <a href="/docs/">the docs</a>.'


@app.route("/contacts")
def list_contacts():
    """List all contacts in the address book.

    Returns a JSON array of contact objects, each with ``id``, ``name``,
    and ``email`` fields.  Supports pagination via ``?page=`` and
    ``?limit=`` query parameters.
    """
    return [
        {"id": 1, "name": "Alice", "email": "alice@example.com"},
        {"id": 2, "name": "Bob", "email": "bob@example.com"},
        {"id": 3, "name": "Carol", "email": "carol@example.com"},
    ]


@app.route("/contacts/{contact_id:int}")
def get_contact(contact_id: int):
    """Retrieve a single contact by their numeric ID.

    Returns a contact object with ``id``, ``name``, ``email``, and
    ``created_at`` fields.  Returns 404 if the contact does not exist.
    """
    return {
        "id": contact_id,
        "name": "Alice",
        "email": "alice@example.com",
        "created_at": "2026-01-15T10:30:00Z",
    }


@app.route("/contacts", methods=["POST"])
def create_contact(request: Request):
    """Create a new contact from JSON or form data.

    Expects ``name`` (required) and ``email`` (required) fields.
    Returns the created contact with a generated ``id``.
    """
    return {"status": "created", "id": 4}


@app.route("/contacts/{contact_id:int}", methods=["PUT"])
def update_contact(request: Request, contact_id: int):
    """Update an existing contact by ID.

    Accepts partial updates — only fields present in the request body
    are modified.  Returns the updated contact object.
    """
    return {"status": "updated", "id": contact_id}


@app.route("/contacts/{contact_id:int}", methods=["DELETE"])
def delete_contact(contact_id: int):
    """Delete a contact by ID.

    Returns 204 No Content on success.  Idempotent — deleting a
    non-existent contact returns 204 without error.
    """
    return {"status": "deleted"}


@app.route("/search")
def search_contacts(request: Request):
    """Search contacts by name or email.

    Query parameters:
    - ``q`` — search query (matches name and email)
    - ``limit`` — max results to return (default: 20)
    """
    q = request.query.get("q", "")
    return {"query": q, "results": []}


# ── Tools ───────────────────────────────────────────────────────────────


@app.tool("echo", description="Echo back the input message")
def echo(message: str) -> str:
    """Simple echo tool for testing MCP integration."""
    return message


@app.tool("lookup_contact", description="Look up a contact by name or email")
def lookup_contact(query: str, exact: bool = False) -> list[dict]:
    """Search the address book for contacts matching the query.

    When ``exact`` is True, only exact matches are returned.
    Otherwise, partial matches on name and email are included.
    """
    return [{"id": 1, "name": "Alice", "email": "alice@example.com"}]


@app.tool("create_note", description="Create a note attached to a contact")
def create_note(contact_id: int, text: str, priority: str = "normal") -> dict:
    """Attach a text note to an existing contact.

    Priority levels: ``low``, ``normal``, ``high``.
    """
    return {"id": 1, "contact_id": contact_id, "text": text, "priority": priority}


# ── Docs Plugin ─────────────────────────────────────────────────────────

app.mount(
    "/docs",
    DocsPlugin(
        content_dir=CONTENT_DIR,
        title="Docs Site",
        autodoc=True,
        tools=True,
    ),
)


if __name__ == "__main__":
    app.run()
