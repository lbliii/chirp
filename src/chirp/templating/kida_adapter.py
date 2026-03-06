"""Kida-backed implementation of TemplateAdapter."""

from __future__ import annotations

from typing import Any

from kida import Environment


class KidaAdapter:
    """TemplateAdapter implementation using Kida's public block/layout APIs."""

    def __init__(self, env: Environment) -> None:
        self._env = env

    def render_template(self, template: str, context: dict[str, Any]) -> str:
        """Render a full template to HTML."""
        tmpl = self._env.get_template(template)
        return tmpl.render(context)

    def render_block(self, template: str, block: str, context: dict[str, Any]) -> str:
        """Render a named block from a template."""
        tmpl = self._env.get_template(template)
        return tmpl.render_block(block, context)

    def compose_layout(
        self,
        template: str,
        block_overrides: dict[str, str],
        context: dict[str, Any],
    ) -> str:
        """Render template with pre-rendered HTML injected into blocks."""
        tmpl = self._env.get_template(template)
        return tmpl.render_with_blocks(block_overrides, **context)
