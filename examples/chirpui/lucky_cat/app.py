"""Lucky Cat — CHIRP bootstrap: wiring registration + mount_pages.

DOMAIN modules: feed, wallet, trade_store, … — see DESIGN.md.
Run: PYTHONPATH=src python examples/chirpui/lucky_cat/app.py
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from wiring.app_factory import PAGES_DIR, app, register_chirp_ui
from wiring import middleware, signals
from wiring.routes import register as register_routes

register_chirp_ui()
middleware.register(app)
import wiring.signals  # noqa: F401,E402 — registers @app.signal before mount_pages

register_routes(app)

app.register_oob_region(
    "watchlist_count_oob", target_id="watchlist-count", swap="innerHTML", wrap=False
)

app.mount_pages(str(PAGES_DIR))

if __name__ == "__main__":
    app.run()
