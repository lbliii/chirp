"""Kida environment setup and app binding.

Creates a kida Environment from chirp's AppConfig and binds
user-registered filters and globals. The environment is created
once during App._freeze() and passed through the request pipeline.
"""

from collections.abc import Callable
from typing import Any

from kida import Environment, FileSystemLoader

from chirp.config import AppConfig
from chirp.templating.returns import Fragment, Template


def create_environment(
    config: AppConfig,
    filters: dict[str, Callable[..., Any]],
    globals_: dict[str, Any],
) -> Environment:
    """Create a kida Environment from app configuration.

    Called once during ``App._freeze()``. The returned environment
    is immutable for the lifetime of the app.
    """
    env = Environment(
        loader=FileSystemLoader(str(config.template_dir)),
        autoescape=config.autoescape,
        auto_reload=config.debug,
        trim_blocks=config.trim_blocks,
        lstrip_blocks=config.lstrip_blocks,
    )

    # Register user-defined filters
    if filters:
        env.update_filters(filters)

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
