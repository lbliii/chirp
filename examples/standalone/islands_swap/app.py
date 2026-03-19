"""Islands + htmx Fragment Swap — island inside dynamically swapped content.

Demonstrates the islands lifecycle with htmx swaps: a "Load widget" button
fetches a fragment containing an island. The runtime unmounts before the swap
and mounts the new island after. Click "Reload" to swap again — unmount/remount.

Demonstrates:
- AppConfig(islands=True)
- Island inside htmx-swapped fragment
- htmx:beforeSwap / htmx:afterSwap integration
- Multiple swaps (reload) trigger full unmount/remount cycle

Run:
    python app.py
"""

from pathlib import Path

from chirp import App, AppConfig, Fragment, Request, Template

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
def index(request: Request):
    """Full page with load button."""
    return Template("index.html", has_widget=False)


@app.route("/widget")
def widget_fragment(request: Request):
    """Fragment containing an island — swapped in by htmx."""
    return Fragment("_widget.html", "widget_block", initial_count=0)


if __name__ == "__main__":
    app.run()
