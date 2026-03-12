"""Contacts Shell — chirp-ui app shell with mounted pages and inline CRUD.

Demonstrates:
- ``use_chirp_ui(app)`` with ``app.mount_pages()``
- ``chirpui/app_shell_layout.html`` for a persistent app shell
- route-scoped ``ShellActions`` from ``_context.py``
- query-backed filtering with inline row editing

Run:
    python app.py
"""

import sys
from pathlib import Path

from chirp import App, AppConfig, use_chirp_ui

ROOT_DIR = Path(__file__).parent
PAGES_DIR = ROOT_DIR / "pages"

sys.path.insert(0, str(ROOT_DIR))
sys.modules.pop("contacts_shell_store", None)

from contacts_shell_store import reset_store

config = AppConfig(template_dir=PAGES_DIR, debug=True)
app = App(config=config)

use_chirp_ui(app)
reset_store()
app.mount_pages(str(PAGES_DIR))


if __name__ == "__main__":
    app.run()
