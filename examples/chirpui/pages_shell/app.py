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

from chirp import App, AppConfig, Page, use_chirp_ui

PAGES_DIR = Path(__file__).parent / "pages"

app = App(AppConfig(template_dir=PAGES_DIR, debug=True))
use_chirp_ui(app)
app.mount_pages(str(PAGES_DIR))


@app.error(404)
def not_found():
    return (
        Page("error.html", "page_root", error_code="404", error_heading="", error_description=""),
        404,
    )


@app.error(500)
def server_error():
    return (
        Page("error.html", "page_root", error_code="500", error_heading="", error_description=""),
        500,
    )


if __name__ == "__main__":
    app.run()
