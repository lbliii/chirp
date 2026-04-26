"""Forum Shell — distilled app-shell forum patterns for ChirpUI.

Inspired by larger PBP/community apps, but intentionally compact.
"""

import sys
from pathlib import Path

from chirp import App, AppConfig, JSONResponse, Request, use_chirp_ui

ROOT_DIR = Path(__file__).parent
PAGES_DIR = ROOT_DIR / "pages"

sys.path.insert(0, str(ROOT_DIR))
sys.modules.pop("forum_store", None)

from forum_store import reset_store, store

app = App(AppConfig(template_dir=PAGES_DIR, debug=True))
use_chirp_ui(app)
app.register_oob_region(
    "unread_count_oob",
    target_id="forum-unread-count",
    swap="innerHTML",
    wrap=True,
)
reset_store()
app.mount_pages(str(PAGES_DIR))


@app.route("/")
def index():
    from chirp import Redirect

    return Redirect(app.url_for("boards"))


@app.route("/mentionables/search")
def mentionable_search(request: Request):
    return JSONResponse.from_value({"items": store.mentionables(request.query.get("q", ""))})


if __name__ == "__main__":
    app.run()
