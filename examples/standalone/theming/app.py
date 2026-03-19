"""Theming — dark/light mode with CSS custom properties.

Shows how to implement theme modes in a Chirp app using only the
web platform: CSS custom properties, ``prefers-color-scheme``, and a
tiny ``localStorage`` toggle.  No framework magic required.

Demonstrates:
- CSS custom properties as design tokens
- ``prefers-color-scheme`` media query (automatic OS preference)
- ``data-theme`` attribute override (user toggle)
- ``localStorage`` persistence across navigations
- Anti-FOUC inline script in ``<head>``

Run:
    python app.py
"""

from pathlib import Path

from chirp import App, AppConfig, Template

TEMPLATES_DIR = Path(__file__).parent / "templates"

config = AppConfig(template_dir=TEMPLATES_DIR)
app = App(config=config)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    """Home page — shows themed UI elements."""
    return Template("index.html")


@app.route("/about")
def about():
    """Second page — proves theme persists across navigation."""
    return Template("about.html")


if __name__ == "__main__":
    app.run()
