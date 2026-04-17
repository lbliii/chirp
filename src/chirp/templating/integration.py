"""Kida environment setup and app binding.

Creates a kida Environment from chirp's AppConfig and binds
user-registered filters and globals. The environment is created
once during App._freeze() and passed through the request pipeline.
"""

import warnings
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any, cast

from kida import ChoiceLoader, Environment, FileSystemLoader, PackageLoader

from chirp.config import AppConfig
from chirp.templating.filters import BUILTIN_FILTERS, BUILTIN_GLOBALS
from chirp.templating.returns import Fragment, Template
from chirp.templating.suspense import DEFERRED

#: Capture (template_name, context) from every full-page render.
#: ``chirp.freeze`` sets this ContextVar so it can re-render pages with
#: live-block placeholders. Outside of freeze this is ``None`` and
#: ``render_template`` skips the capture entirely.
_render_capture: ContextVar[list[tuple[str, dict[str, Any]]] | None] = ContextVar(
    "chirp_render_capture", default=None
)


def _is_chirp_ui_filter_override(name: str, func: Callable[..., Any]) -> bool:
    """True when *func* is chirp-ui's implementation replacing chirp stubs for the UI kit."""

    if name not in BUILTIN_FILTERS or func is BUILTIN_FILTERS[name]:
        return False
    return getattr(func, "__module__", "").startswith("chirp_ui")


_CHIRP_UI_FILTER_NAMES = (
    "bem",
    "contrast_text",
    "deprecate_param",
    "field_errors",
    "html_attrs",
    "icon",
    "resolve_color",
    "resolve_status_variant",
    "sanitize_color",
    "shell_action_btn_variant",
    "validate_size",
    "validate_variant",
    "validate_variant_block",
    "value_type",
)

_CHIRP_UI_GLOBAL_NAMES = ("build_hx_attrs", "check_required_id")


def _ensure_chirp_ui_filters(env: Environment) -> None:
    """Ensure chirp-ui required filters and globals exist when chirp-ui templates are loadable.

    When chirp adds chirp-ui's PackageLoader, those templates require a set of
    filters and globals to compile. This fallback mirrors the surface registered
    by ``chirp_ui.register_filters`` so the env is self-consistent even when
    the app did not call ``use_chirp_ui``. Kept name-by-name (rather than calling
    chirp-ui's own registrar) because Kida's ``Environment`` doesn't implement
    the full ``TemplateFilterApp`` protocol.
    See docs/rfcs/001-component-filter-contract.md.
    """
    try:
        import chirp_ui  # noqa: F401
    except ImportError:
        return
    try:
        import chirp_ui.filters as _filters
    except ImportError:
        return

    # Overwrite chirp's stubs (e.g. ``bem``) with chirp-ui's real implementations
    # when both exist — the stubs only accept a subset of the real kwargs, so
    # letting the stub win breaks chirp-ui templates that pass newer kwargs.
    # This matches what chirp_ui.register_filters would do if the user had
    # called use_chirp_ui(app).
    resolved: dict[str, Callable[..., Any]] = {}
    for name in _CHIRP_UI_FILTER_NAMES:
        func = getattr(_filters, name, None)
        if func is None and name == "icon":
            try:
                from chirp_ui.icons import icon as _icon

                func = _icon
            except ImportError:
                func = None
        if func is not None:
            resolved[name] = func
    if resolved:
        env.update_filters(cast(dict[str, Callable[..., Any]], resolved))

    # Ensure chirp-ui globals (functions used directly in templates, not as filters)
    env_globals = env.globals if hasattr(env, "globals") else {}
    for name in _CHIRP_UI_GLOBAL_NAMES:
        if name in env_globals:
            continue
        func = getattr(_filters, name, None)
        if func is not None:
            env.add_global(name, func)
    if "tab_is_active" not in env_globals:
        try:
            from chirp_ui.route_tabs import tab_is_active

            env.add_global("tab_is_active", tab_is_active)
        except ImportError:
            pass
    if "route_link_attrs" not in env_globals:
        try:
            from chirp_ui.filters import make_route_link_attrs

            env.add_global("route_link_attrs", make_route_link_attrs())
        except ImportError:
            pass


def create_environment(
    config: AppConfig,
    filters: dict[str, Callable[..., Any]],
    globals_: dict[str, Any],
    plugin_loaders: list | None = None,
) -> Environment:
    """Create a kida Environment from app configuration.

    Called once during ``App._freeze()``. The returned environment
    is immutable for the lifetime of the app.

    Supports multiple template directories via ``config.component_dirs``
    for component libraries, partials, and shared templates.
    Extra loaders (CMS, DB, state) are tried first when configured.
    """
    loaders = list(config.extra_loaders)
    loaders.append(FileSystemLoader(str(config.template_dir)))

    # Add component directories (for components, partials, shared templates)
    loaders.extend(FileSystemLoader(str(d)) for d in config.component_dirs)

    # Add chirp's built-in macros
    loaders.append(PackageLoader("chirp.templating", "macros"))

    # Add plugin template loaders
    if plugin_loaders:
        loaders.extend(plugin_loaders)

    # Auto-detect chirp-ui if installed
    try:
        import chirp_ui  # noqa: F401

        loaders.append(PackageLoader("chirp_ui", "templates"))
    except ImportError:
        pass

    loader = ChoiceLoader(loaders)
    env = Environment(
        loader=loader,
        autoescape=config.autoescape,
        auto_reload=config.debug,
        trim_blocks=config.trim_blocks,
        lstrip_blocks=config.lstrip_blocks,
        static_context=dict(config.static_context) if config.static_context else None,
    )

    # Register the ``deferred`` template test for Suspense sentinel checks.
    # Usage: ``{% if x is deferred %}`` — preferred over ``{% if x is not none %}``.
    env.add_test("deferred", lambda val: val is DEFERRED)

    # Register chirp's built-in filters (field_errors, qs, etc.)
    env.update_filters(BUILTIN_FILTERS)

    # When chirp-ui templates are loadable, ensure required filters exist.
    # Fallback for older chirp or apps that didn't call register_filters.
    # Runs before user filters so user registrations still win.
    # See docs/rfcs/001-component-filter-contract.md
    _ensure_chirp_ui_filters(env)

    # Register user-defined filters (may override built-ins)
    if filters:
        for name, func in filters.items():
            if (
                name in BUILTIN_FILTERS
                and func is not BUILTIN_FILTERS[name]
                and not _is_chirp_ui_filter_override(name, func)
            ):
                warnings.warn(
                    f"User filter {name!r} shadows built-in chirp filter. "
                    "This may cause unexpected template behavior.",
                    UserWarning,
                    stacklevel=2,
                )
        env.update_filters(filters)

    # Register user-defined globals
    for name, value in BUILTIN_GLOBALS.items():
        env.add_global(name, value)

    # Globals that are intentional placeholders (None-valued) meant to be
    # overridden per-request — don't warn when user code sets these.
    overridable_globals = frozenset({"shell_actions"})

    # Register user-defined globals
    for name, value in globals_.items():
        if name in BUILTIN_GLOBALS and name not in overridable_globals:
            warnings.warn(
                f"User global {name!r} shadows built-in chirp global. "
                "This may cause unexpected template behavior.",
                UserWarning,
                stacklevel=2,
            )
        env.add_global(name, value)

    return env


def render_template(env: Environment, tpl: Template) -> str:
    """Render a full template to string."""
    template = env.get_template(tpl.template_name)
    capture = _render_capture.get(None)
    if capture is not None:
        capture.append((tpl.template_name, dict(tpl.context)))
    return template.render(tpl.context)


def render_fragment(env: Environment, frag: Fragment) -> str:
    """Render a named block from a template to string.

    Raises ``BlockNotFoundError`` (a ``KeyError`` subclass) when the named
    block does not exist in the template. Unifies the error contract across
    both OOB pipelines — region updates (PR #90) and ``OOB(...)`` return
    values both surface the same exception type with the same message shape.
    """
    template = env.get_template(frag.template_name)
    if frag.block_name not in template.list_blocks():
        from chirp.errors import BlockNotFoundError

        raise BlockNotFoundError(template=frag.template_name, block=frag.block_name)
    return template.render_block(frag.block_name, frag.context)
