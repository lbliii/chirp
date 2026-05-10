"""Kida-backed implementation of TemplateAdapter."""

from typing import Any

from kida import Environment
from kida.exceptions import TemplateRuntimeError


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
        try:
            return tmpl.render_block(block, context)
        except TemplateRuntimeError as exc:
            message = getattr(exc, "message", str(exc))
            if f"Block {block!r} not found" in message:
                raise KeyError(message) from exc
            raise

    def compose_layout(
        self,
        template: str,
        block_overrides: dict[str, str],
        context: dict[str, Any],
    ) -> str:
        """Render template with pre-rendered HTML injected into blocks."""
        tmpl = self._env.get_template(template)
        return tmpl.render_with_blocks(block_overrides, **context)

    def template_metadata(self, template: str) -> object | None:
        """Return TemplateMetadata for block validation and composition planning."""
        from kida.environment.exceptions import (
            TemplateNotFoundError,
            TemplateSyntaxError,
        )

        try:
            tmpl = self._env.get_template(template)
            return tmpl.template_metadata()
        except TemplateNotFoundError, TemplateSyntaxError:
            return None
