"""Kida environment setup and app binding.

Creates a kida Environment from chirp's AppConfig and binds
user-registered filters and globals. The environment is created
once during App._freeze() and passed through the request pipeline.
"""

from collections.abc import Callable
from typing import Any

from kida import ChoiceLoader, Environment, FileSystemLoader, PackageLoader

from chirp.config import AppConfig
from chirp.templating.filters import BUILTIN_FILTERS, BUILTIN_GLOBALS
from chirp.templating.returns import Fragment, Template


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
    """
    loaders = [
        FileSystemLoader(str(config.template_dir)),
    ]

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
