"""chirp-ui integration — register static files for chirp-ui components.

Requires: pip install chirp-ui

Usage::

    from chirp import App
    from chirp.ext.chirp_ui import use_chirp_ui

    app = App(AppConfig(template_dir="templates"))
    use_chirp_ui(app)
    chirp_ui.register_filters(app)  # for bem, field_errors used by components
    app.run()
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chirp.app import App


def use_chirp_ui(app: App, prefix: str = "/static") -> None:
    """Register chirp-ui static files (CSS, themes) with the app.

    Call after App creation. Serves chirpui.css, themes/, chirpui-transitions.css
    from the chirp-ui package. Also call chirp_ui.register_filters(app) so
    chirp-ui components (badge, alert, etc.) have access to bem and field_errors.

    Raises ImportError if chirp-ui is not installed.
    """
    import chirp_ui

    from chirp.middleware.static import StaticFiles

    app.add_middleware(StaticFiles(directory=str(chirp_ui.static_path()), prefix=prefix))
