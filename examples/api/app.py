"""API — pure JSON REST API (no HTML).

CRUD for a simple "items" resource. Demonstrates Chirp for API-only apps:
dict/list returns become JSON, path parameters, request.json() for POST/PUT,
and optional CORSMiddleware for cross-origin consumers.

Run:
    cd examples/api && python app.py
"""

import threading
from dataclasses import dataclass

from chirp import App, Request
from chirp.middleware.builtin import CORSConfig, CORSMiddleware

app = App()

app.add_middleware(CORSMiddleware(CORSConfig(
    allow_origins=("*",),
    allow_methods=("GET", "POST", "PUT", "DELETE", "OPTIONS"),
    allow_headers=("Content-Type",),
)))


# ---------------------------------------------------------------------------
# In-memory storage (thread-safe for free-threading)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Item:
    id: int
    title: str
    done: bool


_items: dict[int, Item] = {}
_next_id = 1
_lock = threading.Lock()


def _get_next_id() -> int:
    global _next_id
    with _lock:
        n = _next_id
        _next_id += 1
        return n


def _to_dict(item: Item) -> dict:
    return {"id": item.id, "title": item.title, "done": item.done}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/api/items")
async def list_items(request: Request):
    """List items with optional limit and offset."""
    limit = min(max(request.query.get_int("limit", default=50) or 50, 1), 100)
    offset = max(request.query.get_int("offset", default=0) or 0, 0)

    with _lock:
        all_items = sorted(_items.values(), key=lambda x: x.id)
    page = all_items[offset : offset + limit]

    return {
        "data": [_to_dict(i) for i in page],
        "meta": {"limit": limit, "offset": offset, "total": len(all_items)},
    }


@app.route("/api/items/{item_id}")
def get_item(item_id: int):
    """Get a single item by ID."""
    with _lock:
        item = _items.get(item_id)
    if item is None:
        return ({"error": "Not found", "status": 404}, 404)
    return {"data": _to_dict(item)}


@app.route("/api/items", methods=["POST"])
async def create_item(request: Request):
    """Create a new item."""
    body = await request.json()
    title = body.get("title", "").strip()
    if not title:
        return ({"error": "title is required", "status": 400}, 400)

    with _lock:
        item_id = _get_next_id()
        item = Item(id=item_id, title=title, done=False)
        _items[item_id] = item

    return {"data": _to_dict(item)}, 201


@app.route("/api/items/{item_id}", methods=["PUT"])
async def update_item(item_id: int, request: Request):
    """Update an existing item."""
    with _lock:
        item = _items.get(item_id)
    if item is None:
        return ({"error": "Not found", "status": 404}, 404)

    body = await request.json()
    raw_title = body.get("title")
    raw_done = body.get("done")
    title = str(raw_title).strip() if raw_title is not None else item.title
    done = bool(raw_done) if raw_done is not None else item.done

    updated = Item(id=item.id, title=title, done=done)
    with _lock:
        _items[item_id] = updated

    return {"data": _to_dict(updated)}


@app.route("/api/items/{item_id}", methods=["DELETE"])
def delete_item(item_id: int):
    """Delete an item."""
    with _lock:
        item = _items.pop(item_id, None)
    if item is None:
        return ({"error": "Not found", "status": 404}, 404)
    return {"data": _to_dict(item)}


@app.error(404)
def not_found(request: Request):
    """Global 404 for non-API routes."""
    return {"error": "Not found", "status": 404}


if __name__ == "__main__":
    app.run()
