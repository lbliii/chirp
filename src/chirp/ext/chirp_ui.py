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

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chirp.app import App

from chirp.http.request import Request
from chirp.middleware.protocol import AnyResponse, Middleware, Next


class _ChirpUIStrictMiddleware(Middleware):
    """Middleware that sets chirp-ui strict mode per request for variant validation."""

    __slots__ = ("_strict",)

    def __init__(self, strict: bool) -> None:
        self._strict = strict

    async def __call__(self, request: Request, next: Next) -> AnyResponse:
        from chirp_ui import set_strict

        set_strict(self._strict)
        return await next(request)


def use_chirp_ui(app: App, prefix: str = "/static", strict: bool | None = None) -> None:
    """Register chirp-ui static files (CSS, themes) with the app.

    Call after App creation. Serves chirpui.css, themes/, chirpui-transitions.css
    from the chirp-ui package. Also call chirp_ui.register_filters(app) so
    chirp-ui components (badge, alert, etc.) have access to bem and field_errors.

    When strict is None, uses app.config.debug. When True, invalid component
    variants log warnings during template render. When False, no validation.

    Raises ImportError if chirp-ui is not installed.
    """
    import chirp_ui

    from chirp.middleware.static import StaticFiles

    app.add_middleware(StaticFiles(directory=str(chirp_ui.static_path()), prefix=prefix))
    # Add chirp-ui to reload dirs when editable (for dev on component library)
    try:
        chirp_ui_root = Path(chirp_ui.__file__).resolve().parent
        if "chirp-ui" in str(chirp_ui_root):
            app.add_reload_dir(str(chirp_ui_root))
    except AttributeError, OSError:
        pass
    strict_value = strict if strict is not None else app.config.debug
    app.add_middleware(_ChirpUIStrictMiddleware(strict_value))
