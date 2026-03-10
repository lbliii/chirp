"""Kida environment setup and app binding.

Creates a kida Environment from chirp's AppConfig and binds
user-registered filters and globals. The environment is created
once during App._freeze() and passed through the request pipeline.
"""

from collections.abc import Callable
from typing import Any, cast

from kida import ChoiceLoader, Environment, FileSystemLoader, PackageLoader

from chirp.config import AppConfig
from chirp.templating.filters import BUILTIN_FILTERS, BUILTIN_GLOBALS
from chirp.templating.returns import Fragment, Template


def _ensure_chirp_ui_filters(env: Environment) -> None:
    """Ensure chirp-ui required filters exist when chirp-ui templates are loadable.

    When chirp adds chirp-ui's PackageLoader, those templates require bem, field_errors,
    html_attrs, validate_variant, validate_variant_block, validate_size, icon. This
    fallback adds any missing filters so the env is self-consistent.
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


def create_environment(
    config: AppConfig,
    filters: dict[str, Callable[..., Any]],
    globals_: dict[str, Any],
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
    )

    # Register chirp's built-in filters (field_errors, qs, etc.)
    env.update_filters(BUILTIN_FILTERS)

    # Register user-defined filters (may override built-ins)
    if filters:
        env.update_filters(filters)

    # When chirp-ui templates are loadable, ensure required filters exist.
    # Fallback for older chirp or apps that didn't call register_filters.
    # See docs/rfcs/001-component-filter-contract.md
    _ensure_chirp_ui_filters(env)

    # Register user-defined globals
    for name, value in BUILTIN_GLOBALS.items():
        env.add_global(name, value)

    # Register user-defined globals
    for name, value in globals_.items():
        env.add_global(name, value)

    return env


def render_template(env: Environment, tpl: Template) -> str:
    """Render a full template to string."""
    template = env.get_template(tpl.name)
    return template.render(tpl.context)


def render_fragment(env: Environment, frag: Fragment) -> str:
    """Render a named block from a template to string."""
    template = env.get_template(frag.template_name)
    return template.render_block(frag.block_name, frag.context)
