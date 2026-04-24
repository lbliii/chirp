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
from chirp.middleware.csrf import CSRFMiddleware
from chirp.middleware.sessions import SessionConfig, SessionMiddleware

ROOT_DIR = Path(__file__).parent
PAGES_DIR = ROOT_DIR / "pages"

sys.path.insert(0, str(ROOT_DIR))
sys.modules.pop("contacts_shell_store", None)

from chirp_ui import register_colors
from contacts_shell_store import GROUP_COLORS, reset_store

config = AppConfig(template_dir=PAGES_DIR, debug=True)
app = App(config=config)

use_chirp_ui(app)
register_colors(GROUP_COLORS)
app.add_middleware(SessionMiddleware(SessionConfig(secret_key="contacts-shell-dev-secret")))
app.add_middleware(CSRFMiddleware())
reset_store()
app.mount_pages(str(PAGES_DIR))


if __name__ == "__main__":
    app.run()
