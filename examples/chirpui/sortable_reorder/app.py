"""Recipe Builder — Alpine + HTMX drag-and-drop without Sortable.js.

Demonstrates native HTML5 drag-and-drop with chirp-ui sortable_list,
structured recipe steps, and split layout with live preview.

Run:
    pip install chirp[ui]
    python app.py
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

if "store" in sys.modules:
    _loaded = Path(sys.modules["store"].__file__).resolve()
    if _loaded != (ROOT_DIR / "store.py").resolve():
        del sys.modules["store"]

from store import add_step, get_steps, remove_step, reorder_steps, reset

from chirp import App, AppConfig, Fragment, Request, use_chirp_ui
from chirp.middleware.csrf import CSRFConfig, CSRFMiddleware
from chirp.middleware.sessions import SessionConfig, SessionMiddleware

PAGES_DIR = Path(__file__).parent / "pages"

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

reset()
app.mount_pages(str(PAGES_DIR))


@app.route("/steps", methods=["POST"])
async def add_step_route(request: Request):
    form = await request.form()
    instruction = (form.get("instruction") or "").strip()
    duration = (form.get("duration") or "").strip()
    note = (form.get("note") or "").strip()
    if instruction:
        add_step(instruction, duration, note)
    steps = get_steps()
    return Fragment("page.html", "recipe_content", steps=steps)


@app.route("/steps/delete", methods=["POST"])
async def delete_step_route(request: Request):
    form = await request.form()
    step_id = int(form.get("step_id") or "0")
    if step_id:
        remove_step(step_id)
    steps = get_steps()
    return Fragment("page.html", "recipe_content", steps=steps)


@app.route("/reorder", methods=["POST"])
async def reorder_route(request: Request):
    form = await request.form()
    from_idx = int(form.get("from_idx") or "0")
    to_idx = int(form.get("to_idx") or "0")
    reorder_steps(from_idx, to_idx)
    steps = get_steps()
    return Fragment("page.html", "recipe_content", steps=steps)


if __name__ == "__main__":
    app.run()
