"""chirp-ui integration — register static files and filters for chirp-ui components.

Requires: pip install chirp-ui

Usage::

    from chirp import App
    from chirp.ext.chirp_ui import use_chirp_ui

    app = App(AppConfig(template_dir="templates"))
    use_chirp_ui(app)  # Registers static files, filters (bem, field_errors, html_attrs), and middleware
    app.run()
"""


import re
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chirp.app import App
    from chirp.app.state import ContractCheckSnapshot
    from chirp.contracts.types import CheckResult

from chirp.contracts.types import ContractIssue, Severity
from chirp.http.request import Request
from chirp.middleware.inject import StreamingHTMLInject
from chirp.middleware.protocol import AnyResponse, Middleware, Next
from chirp.pages.types import LayoutPreset
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
            scope_name="shell",
        ),
        PageShellTarget(
            target_id="page-root",
            fragment_block="page_root_inner",
            description="Tabbed page shell target that keeps page-root wrappers.",
            scope_name="page",
        ),
        PageShellTarget(
            target_id="page-content-inner",
            fragment_block="page_content",
            triggers_shell_update=False,
            description="Narrow content swap target that skips shell updates.",
            scope_name="content",
        ),
    ),
)

CHIRPUI_APP_SHELL_PRESET = LayoutPreset(
    name="chirpui-app-shell",
    target="body",
    swap_scope_name="shell",
    outlet_target_id="main",
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


def _chirpui_alpine_runtime_snippet(prefix: str) -> str:
    normalized = "/" + prefix.strip("/")
    return (
        f'<script defer src="{normalized}/chirpui-alpine.js" data-chirp="chirpui-alpine"></script>'
    )


def use_chirp_ui(app: App, prefix: str = "/static", strict: bool | None = None) -> None:
    """Register chirp-ui static files (CSS, themes) and filters with the app.

    Call after App creation. Serves chirpui.css, chirpui-alpine.js, themes/,
    chirpui-transitions.css from the chirp-ui package. Automatically registers
    chirp-ui filters (bem, field_errors, html_attrs, validate_variant) so
    components render correctly. It also upgrades chirp-ui's
    ``route_link_attrs`` global to use Chirp's route-aware ``swap_attrs``
    resolution for supported internal links.

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
    if hasattr(app, "template_global"):
        try:
            from chirp_ui.filters import make_route_link_attrs  # ty: ignore[unresolved-import]
        except ImportError:
            make_route_link_attrs = None

        if make_route_link_attrs is not None:
            from chirp.templating.navigation_swap import make_swap_attrs

            swap_helper_cache: dict[str, Any] = {}

            def _swap_resolver(href: str, *, hx_boost: bool = True) -> dict[str, str]:
                runtime = app._runtime_state
                router = runtime.router
                registry = runtime.fragment_target_registry
                if not runtime.frozen or router is None or registry is None:
                    return {}
                helper = swap_helper_cache.get("swap_attrs")
                if helper is None:
                    helper = make_swap_attrs(
                        route_layout_chains=runtime.route_layout_chains,
                        router=router,
                        fragment_target_registry=registry,
                        swap_scope_map=runtime.swap_scope_map,
                    )
                    swap_helper_cache["swap_attrs"] = helper
                return helper(href, hx_boost=hx_boost)

            app.template_global("route_link_attrs")(
                make_route_link_attrs(swap_resolver=_swap_resolver)
            )
    app.add_middleware(StaticFiles(directory=str(chirp_ui.static_path()), prefix=prefix))
    app.add_middleware(
        StreamingHTMLInject(
            _chirpui_alpine_runtime_snippet(prefix),
            before="</head>",
            full_page_only=True,
            dedup_marker='data-chirp="chirpui-alpine"',
        )
    )
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
    app.register_layout_preset(
        CHIRPUI_APP_SHELL_PRESET.name,
        target=CHIRPUI_APP_SHELL_PRESET.target,
        swap_scope_name=CHIRPUI_APP_SHELL_PRESET.swap_scope_name,
        outlet_target_id=CHIRPUI_APP_SHELL_PRESET.outlet_target_id,
    )
    app.register_swap_scope("shell", "main")
    app.register_swap_scope("page", "page-root")
    app.register_swap_scope("content", "page-content-inner")

    # Register chirp-ui contract checks so app.check() validates component imports
    # and reports design system surface.
    _available = _discover_chirpui_components()
    if _available is not None:
        app.set_contract_check_data("chirpui_components", _available)
        app.register_contract_check(check_chirpui_imports)
        app.register_contract_check(check_design_system_surface)


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
    except ImportError, AttributeError, OSError:
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


def check_design_system_surface(
    snapshot: ContractCheckSnapshot,
    result: CheckResult,
) -> None:
    """Report design system surface and flag descriptor/template mismatches.

    Compares :data:`chirp_ui.components.COMPONENTS` against the actual
    template files on disk.  Components with a declared ``template`` that
    does not exist on disk are flagged as errors.  Templates that exist
    but have no descriptor are flagged as informational notes (not all
    templates need descriptors immediately).
    """
    try:
        from chirp_ui.components import COMPONENTS, design_system_report
    except ImportError:
        return

    available: frozenset[str] | None = snapshot.extras.get("chirpui_components")
    if available is None:
        return

    report = design_system_report()
    stats = report.get("stats", {})

    result.issues.append(
        ContractIssue(
            severity=Severity.INFO,
            category="design_system",
            message=(
                f"chirp-ui design system: "
                f"{stats.get('total_components', 0)} components, "
                f"{stats.get('total_tokens', 0)} tokens"
            ),
        )
    )

    for name, desc in COMPONENTS.items():
        if desc.template and desc.template not in available:
            result.issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="design_system",
                    message=(
                        f'Component "{name}" declares template "{desc.template}" '
                        f"but the file does not exist in chirp-ui templates"
                    ),
                )
            )

    described_templates = {desc.template for desc in COMPONENTS.values() if desc.template}
    undescribed = sorted(available - described_templates)
    if undescribed:
        result.issues.append(
            ContractIssue(
                severity=Severity.INFO,
                category="design_system",
                message=(
                    f"{len(undescribed)} chirp-ui templates without descriptors: "
                    + ", ".join(undescribed[:10])
                    + ("..." if len(undescribed) > 10 else "")
                ),
            )
        )
