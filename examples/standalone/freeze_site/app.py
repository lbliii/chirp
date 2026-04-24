"""Freeze Site — markdown content, layout composition, Alpine, and freeze.

A realistic mini-site that demonstrates the Bengal v2 pattern: a Chirp
app with DocsPlugin for markdown content that freezes to static HTML.

Exercises:
- DocsPlugin with markdown content files
- Layout composition (_layout.html wraps every page)
- Alpine.js injection middleware
- Page() return type (full page vs fragment via DocsPlugin)
- freeze_params auto-registered by DocsPlugin
- Relative URL rewriting for truly static output

Run live:
    uv run python examples/standalone/freeze_site/app.py

Freeze:
    cd examples/standalone/freeze_site
    uv run chirp freeze app:app dist/

Preview frozen:
    python -m http.server --directory dist 8001
"""

from pathlib import Path

from chirp import App, AppConfig, Page
from chirp.docs import DocsPlugin

TEMPLATES_DIR = Path(__file__).parent / "templates"
CONTENT_DIR = Path(__file__).parent / "content"

app = App(
    AppConfig(
        template_dir=TEMPLATES_DIR,
        alpine=True,
    )
)


# ── Routes ────────────────────────────────────────────────────────────────


@app.route("/")
def index():
    return Page(
        "home.html",
        "page_content",
    )


# ── Docs (markdown content) ──────────────────────────────────────────────

app.mount(
    "/docs",
    DocsPlugin(
        content_dir=CONTENT_DIR,
        title="Freeze Demo",
        autodoc=False,
        tools=False,
    ),
)


# ── Entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run()
