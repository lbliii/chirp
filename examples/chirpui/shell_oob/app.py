"""Shell OOB — Team Settings Console.

Demonstrates automatic OOB updates for sidebar, breadcrumbs, title,
and cross-page state via regions. Toggle a setting on /settings and
see the dashboard stats update when you navigate back.

Run:
    python app.py
"""

import sys
from pathlib import Path

from chirp import App, AppConfig, use_chirp_ui

ROOT_DIR = Path(__file__).parent
PAGES_DIR = ROOT_DIR / "pages"

sys.path.insert(0, str(ROOT_DIR))

app = App(AppConfig(template_dir=PAGES_DIR, debug=True))
use_chirp_ui(app)
app.mount_pages(str(PAGES_DIR))

if __name__ == "__main__":
    app.run()
