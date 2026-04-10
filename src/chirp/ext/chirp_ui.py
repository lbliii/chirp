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

import re
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chirp.app import App
    from chirp.app.state import ContractCheckSnapshot
    from chirp.contracts.types import CheckResult

from chirp.contracts.types import ContractIssue, Severity
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
    except AttributeError, OSError:
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

    # Register chirp-ui contract check so app.check() validates component imports.
    _available = _discover_chirpui_components()
    if _available is not None:
        app.set_contract_check_data("chirpui_components", _available)
        app.register_contract_check(check_chirpui_imports)


# ---------------------------------------------------------------------------
# Contract check: validate chirp-ui component imports
# ---------------------------------------------------------------------------

_CHIRPUI_IMPORT_RE = re.compile(
    r"""\{%[-\s]+from\s+["']chirpui/([^"']+)["']""",
)


def _discover_chirpui_components() -> frozenset[str] | None:
    """Return the set of available chirp-ui component template filenames.

    Returns ``None`` if the chirp-ui templates directory cannot be found
    (e.g. editable install without the expected layout).
    """
    try:
        import chirp_ui

        templates_dir = Path(chirp_ui.__file__).resolve().parent / "templates" / "chirpui"
        if templates_dir.is_dir():
            return frozenset(f.name for f in templates_dir.glob("*.html"))
    except Exception:  # noqa: S110
        pass
    return None


def check_chirpui_imports(
    snapshot: ContractCheckSnapshot,
    result: CheckResult,
) -> None:
    """Verify that ``{% from "chirpui/..." %}`` imports reference real components.

    Catches typos like ``{% from "chirpui/cardd.html" import card %}`` at
    startup instead of letting them surface as runtime ``TemplateNotFound``
    errors.
    """
    available: frozenset[str] | None = snapshot.extras.get("chirpui_components")
    if available is None:
        return

    for template_name, source in snapshot.template_sources.items():
        for match in _CHIRPUI_IMPORT_RE.finditer(source):
            component_file = match.group(1)
            if component_file not in available:
                result.issues.append(
                    ContractIssue(
                        severity=Severity.ERROR,
                        category="chirpui_import",
                        message=(f'Unknown chirp-ui component "chirpui/{component_file}"'),
                        template=template_name,
                        details=(
                            "Check for typos. Available components can be listed "
                            'with: python -c "import chirp_ui; print(sorted('
                            "p.name for p in (pathlib.Path(chirp_ui.__file__)"
                            ".parent / 'templates' / 'chirpui').glob('*.html')))\""
                        ),
                    )
                )
