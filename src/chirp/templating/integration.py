"""Kida environment setup and app binding.

Creates a kida Environment from chirp's AppConfig and binds
user-registered filters and globals. The environment is created
once during App._freeze() and passed through the request pipeline.
"""

import warnings
from collections.abc import Callable
from typing import Any, cast

from kida import ChoiceLoader, Environment, FileSystemLoader, PackageLoader

from chirp.config import AppConfig
from chirp.templating.filters import BUILTIN_FILTERS, BUILTIN_GLOBALS
from chirp.templating.returns import Fragment, Template
from chirp.templating.suspense import DEFERRED


def _ensure_chirp_ui_filters(env: Environment) -> None:
    """Ensure chirp-ui required filters and globals exist when chirp-ui templates are loadable.

    When chirp adds chirp-ui's PackageLoader, those templates require bem, field_errors,
    html_attrs, validate_variant, validate_variant_block, validate_size, icon as filters
    and build_hx_attrs, tab_is_active as globals. This fallback adds any missing entries
    so the env is self-consistent.
    See docs/rfcs/001-component-filter-contract.md.
    """
    try:
        import chirp_ui  # noqa: F401
    except ImportError:
        return
    try:
        from chirp_ui.filters import (
            bem,
            field_errors,
            html_attrs,
            validate_size,
            validate_variant,
            validate_variant_block,
        )
    except ImportError:
        return
    try:
        from chirp_ui.filters import icon
    except ImportError:
        from chirp_ui.icons import icon
    chirp_ui_filters = {
        "bem": bem,
        "field_errors": field_errors,
        "html_attrs": html_attrs,
        "icon": icon,
        "validate_size": validate_size,
        "validate_variant": validate_variant,
        "validate_variant_block": validate_variant_block,
    }
    missing = {k: v for k, v in chirp_ui_filters.items() if k not in env.filters}
    if missing:
        env.update_filters(cast(dict[str, Callable[..., Any]], missing))

    # Ensure chirp-ui globals (functions used directly in templates, not as filters)
    chirp_ui_globals: dict[str, Callable[..., Any]] = {}
    try:
        from chirp_ui.filters import build_hx_attrs

        chirp_ui_globals["build_hx_attrs"] = build_hx_attrs
    except ImportError:
        pass
    try:
        from chirp_ui.route_tabs import tab_is_active

        chirp_ui_globals["tab_is_active"] = tab_is_active
    except ImportError:
        pass
    env_globals = env.globals if hasattr(env, "globals") else {}
    for name, func in chirp_ui_globals.items():
        if name not in env_globals:
            env.add_global(name, func)


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

    # Register user-defined filters (may override built-ins)
    if filters:
        for name, func in filters.items():
            if name in BUILTIN_FILTERS and func is not BUILTIN_FILTERS[name]:
                warnings.warn(
                    f"User filter {name!r} shadows built-in chirp filter. "
                    "This may cause unexpected template behavior.",
                    UserWarning,
                    stacklevel=2,
                )
        env.update_filters(filters)

    # When chirp-ui templates are loadable, ensure required filters exist.
    # Fallback for older chirp or apps that didn't call register_filters.
    # See docs/rfcs/001-component-filter-contract.md
    _ensure_chirp_ui_filters(env)

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
    return template.render(tpl.context)


def render_fragment(env: Environment, frag: Fragment) -> str:
    """Render a named block from a template to string."""
    template = env.get_template(frag.template_name)
    return template.render_block(frag.block_name, frag.context)
