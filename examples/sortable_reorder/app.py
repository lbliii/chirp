"""Sortable List Reorder — Alpine + HTMX drag-and-drop without Sortable.js.

Demonstrates native HTML5 drag-and-drop with chirp-ui sortable_list,
Alpine.js for visual feedback (dataset.draggingIdx, overCount), and
HTMX form submission for reorder. No Sortable.js — pure Alpine + HTMX.

Run:
    pip install chirp[ui]
    python app.py
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

from chirp import App, AppConfig, Fragment, Request, use_chirp_ui
from chirp.middleware.csrf import CSRFConfig, CSRFMiddleware
from chirp.middleware.sessions import SessionConfig, SessionMiddleware

from store import add_item, get_items, reorder_items

PAGES_DIR = Path(__file__).parent / "pages"


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

config = AppConfig(template_dir=PAGES_DIR, alpine=True, debug=True)
app = App(config=config)

use_chirp_ui(app)

_secret = "dev-only-not-for-production"
app.add_middleware(
    SessionMiddleware(
        SessionConfig(secret_key=_secret, cookie_name="chirp_session_sortable_reorder")
    )
)
app.add_middleware(CSRFMiddleware(CSRFConfig()))

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

app.mount_pages(str(PAGES_DIR))


@app.route("/items", methods=["POST"])
async def add_item_route(request: Request):
    form = await request.form()
    name = (form.get("name") or "").strip()
    if name:
        add_item(name)
    items = get_items()
    return Fragment("page.html", "item_list", items=items)


@app.route("/reorder", methods=["POST"])
async def reorder_route(request: Request):
    form = await request.form()
    from_idx = int(form.get("from_idx") or "0")
    to_idx = int(form.get("to_idx") or "0")
    reorder_items(from_idx, to_idx)
    items = get_items()
    return Fragment("page.html", "item_list", items=items)


if __name__ == "__main__":
    app.run()
