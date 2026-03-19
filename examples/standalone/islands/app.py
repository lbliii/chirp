"""Islands — no-build client-managed surfaces with island_attrs().

Demonstrates Chirp's islands runtime: server-rendered HTML with isolated
client-owned widgets. Uses AppConfig(islands=True), island_attrs() for mount
metadata, and a plain ES module adapter loaded via data-island-src.

Demonstrates:
- AppConfig(islands=True) for runtime injection
- island_attrs() for safe mount attribute generation
- SSR fallback inside the mount root (no-JS mode)
- Dynamic adapter loading via data-island-src
- chirp:island:mount lifecycle

Run:
    python app.py
"""

from pathlib import Path

from chirp import App, AppConfig, Template

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

config = AppConfig(
    template_dir=TEMPLATES_DIR,
    static_dir=STATIC_DIR,
    islands=True,
    debug=True,
)
app = App(config=config)


@app.route("/")
def index():
    """Home page with a counter island."""
    return Template("index.html", initial_count=0)


if __name__ == "__main__":
    app.run()
