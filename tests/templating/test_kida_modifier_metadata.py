"""Downstream contract pilot for Kida's literal block modifiers."""

from __future__ import annotations

import pytest
from kida import DictLoader, Environment, TemplateMetadata

from chirp.templating.kida_adapter import KidaAdapter


@pytest.mark.issue(347)
def test_adapter_surfaces_typed_block_and_fragment_modifiers_without_render_drift() -> None:
    env = Environment(
        loader=DictLoader(
            {
                "page.html": (
                    '{% block chart enhancement="sse" fallback="table" %}'
                    "<div>{{ value }}</div>{% end %}"
                    '{% fragment updates transport="sse" %}'
                    "<span>{{ message }}</span>{% end %}"
                )
            }
        )
    )
    adapter = KidaAdapter(env)

    metadata = adapter.template_metadata("page.html")

    assert isinstance(metadata, TemplateMetadata)
    chart = metadata.blocks["chart"]
    updates = metadata.blocks["updates"]
    assert [(item.name, item.value) for item in chart.modifiers] == [
        ("enhancement", "sse"),
        ("fallback", "table"),
    ]
    assert chart.get_modifier("enhancement") is not None
    assert updates.get_modifier("transport") is not None
    assert adapter.render_template("page.html", {"value": "ready"}) == "<div>ready</div>"
    assert adapter.render_block("page.html", "updates", {"message": "live"}) == (
        "<span>live</span>"
    )
