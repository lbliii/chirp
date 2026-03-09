"""Shell OOB — prototype for AST-powered shell updates.

Demonstrates automatic OOB updates for sidebar, breadcrumbs, and title
on hx-boost navigation using Kida's AST metadata.

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
