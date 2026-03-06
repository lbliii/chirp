"""Template adapter seam — abstracts Kida for composition rendering.

Chirp uses this protocol so the composition layer stays independent of
Kida internals. The KidaAdapter routes render_template, render_block,
compose_layout, and template_metadata through Kida's public APIs.
"""

from __future__ import annotations

from typing import Any, Protocol


class TemplateAdapter(Protocol):
    """Protocol for template rendering used by the composition layer.

    Implementations wrap Kida (or another engine) without exposing
    framework-specific details to negotiation.
    """

    def render_template(self, template: str, context: dict[str, Any]) -> str:
        """Render a full template to HTML."""
        ...

    def render_block(self, template: str, block: str, context: dict[str, Any]) -> str:
        """Render a named block from a template."""
        ...

    def compose_layout(
        self,
        template: str,
        block_overrides: dict[str, str],
        context: dict[str, Any],
    ) -> str:
        """Render template with pre-rendered HTML injected into blocks."""
        ...

    def template_metadata(self, template: str) -> object | None:
        """Return structure metadata for a template, or None if unavailable.

        Used for block validation and composition planning. KidaAdapter
        returns TemplateMetadata. Adapters that do not support metadata
        may return None.
        """
        ...
