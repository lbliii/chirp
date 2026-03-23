"""chirp-ui integration — register static files and filters for chirp-ui components.

Requires: pip install chirp-ui

Usage::

    from chirp import App
    from chirp.ext.chirp_ui import use_chirp_ui

    app = App(AppConfig(template_dir="templates"))
    use_chirp_ui(app)  # Registers static files, filters (bem, field_errors, html_attrs), and middleware
    app.run()
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chirp.app import App

from chirp.http.request import Request
from chirp.middleware.protocol import AnyResponse, Middleware, Next
from chirp.templating.fragment_target_registry import PageShellContract, PageShellTarget

# Deprecated: these constants moved from chirp.templating.render_plan.
# Import from chirp.ext.chirp_ui if needed. Will be removed in the next major.
CHIRPUI_BREADCRUMBS_TARGET = "chirpui-topbar-breadcrumbs"
CHIRPUI_SIDEBAR_TARGET = "chirpui-sidebar-nav"
CHIRPUI_DOCUMENT_TITLE_TARGET = "chirpui-document-title"
BREADCRUMBS_OOB_BLOCK = "breadcrumbs_oob"
SIDEBAR_OOB_BLOCK = "sidebar_oob"
TITLE_OOB_BLOCK = "title_oob"

CHIRPUI_PAGE_SHELL_CONTRACT = PageShellContract(
    name="chirpui-app-shell",
    description="Canonical ChirpUI page shell contract for app-shell and tabbed page layouts.",
    targets=(
        PageShellTarget(
            target_id="main",
            fragment_block="page_root",
            description="Sidebar and boosted page navigation target.",
        ),
        PageShellTarget(
            target_id="page-root",
            fragment_block="page_root_inner",
            description="Tabbed page shell target that keeps page-root wrappers.",
        ),
        PageShellTarget(
            target_id="page-content-inner",
            fragment_block="page_content",
            triggers_shell_update=False,
            description="Narrow content swap target that skips shell updates.",
        ),
    ),
)


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
    """Register chirp-ui static files (CSS, themes) and filters with the app.

    Call after App creation. Serves chirpui.css, themes/, chirpui-transitions.css
    from the chirp-ui package. Automatically registers chirp-ui filters (bem,
    field_errors, html_attrs, validate_variant) so components render correctly.

    Alpine.js is auto-enabled (chirp-ui components require it). Chirp is the
    single authority for Alpine injection — the ``app_shell_layout.html`` does
    not include its own Alpine scripts.

    When strict is None, uses app.config.debug. When True, invalid component
    variants log warnings during template render. When False, no validation.

    Raises ImportError if chirp-ui is not installed.
    """
    import chirp_ui

    from chirp.middleware.static import StaticFiles

    if not app.config.alpine:
        app.bind_config(replace(app.config, alpine=True))

    chirp_ui.register_filters(app)
    app.add_middleware(StaticFiles(directory=str(chirp_ui.static_path()), prefix=prefix))
    # Add chirp-ui to reload dirs when editable (for dev on component library)
    try:
        chirp_ui_root = Path(chirp_ui.__file__).resolve().parent
        if "chirp-ui" in str(chirp_ui_root):
            app.add_reload_dir(str(chirp_ui_root))
    except (AttributeError, OSError):
        pass
    strict_value = strict if strict is not None else app.config.debug
    app.add_middleware(_ChirpUIStrictMiddleware(strict_value))

    app.register_oob_region(
        "breadcrumbs_oob",
        target_id="chirpui-topbar-breadcrumbs",
        swap="innerHTML",
        wrap=True,
    )
    app.register_oob_region(
        "sidebar_oob",
        target_id="chirpui-sidebar-nav",
        swap="innerHTML",
        wrap=True,
    )
    app.register_oob_region(
        "title_oob",
        target_id="chirpui-document-title",
        swap="true",
        wrap=False,
    )

    app.register_page_shell_contract(CHIRPUI_PAGE_SHELL_CONTRACT)
