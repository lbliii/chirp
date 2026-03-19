"""Islands + App Shell — islands inside ChirpUI shell with OOB navigation.

Demonstrates islands coexisting with the app shell: sidebar navigation,
OOB updates for breadcrumbs/title, and a client-managed island in #main.
The island unmounts before htmx swaps and remounts after navigation.

Demonstrates:
- AppConfig(islands=True) with use_chirp_ui
- Islands inside #main with htmx-boosted navigation
- Unmount/remount lifecycle on sidebar link clicks
- StaticFiles for island adapter (counter.js)

Run:
    pip install chirp[ui]
    python app.py
"""

from pathlib import Path

from chirp import App, AppConfig, use_chirp_ui

PAGES_DIR = Path(__file__).parent / "pages"
STATIC_DIR = Path(__file__).parent / "static"

config = AppConfig(
    template_dir=PAGES_DIR,
    static_dir=STATIC_DIR,
    islands=True,
    debug=True,
)
app = App(config=config)
use_chirp_ui(app)
app.mount_pages(str(PAGES_DIR))

if __name__ == "__main__":
    app.run()
