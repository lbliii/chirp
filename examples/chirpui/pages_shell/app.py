"""Mounted pages example with a persistent chirp-ui shell.

Demonstrates:
- ``app.mount_pages()``
- co-located ``page.py`` / ``page.html``
- ``_context.py`` cascade with shell action merging
- ``Page(..., page_block_name="page_root")`` for list pages
- ``Suspense(...)`` on a nested detail page

Run:
    python app.py
"""

from pathlib import Path

from chirp import App, AppConfig, use_chirp_ui

PAGES_DIR = Path(__file__).parent / "pages"

app = App(AppConfig(template_dir=PAGES_DIR, debug=True))
use_chirp_ui(app)
app.mount_pages(str(PAGES_DIR))


if __name__ == "__main__":
    app.run()
