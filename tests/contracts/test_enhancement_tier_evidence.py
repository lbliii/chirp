"""Evidence fixtures for the proposed enhancement-tier contract (#723).

These tests classify facts already published by ``HypermediaProgram``.  They
deliberately do not add or simulate an ``app.check()`` rule: the diagnostic
category and severity table remain a separate approval gate.
"""

from pathlib import Path

import pytest

from chirp import App, AppConfig, Page
from chirp.app.hypermedia_program import stable_identity
from chirp.testing import TestClient, assert_is_full_page, assert_no_full_document


def _enhancement_app(
    template_dir: Path,
    *,
    enhancement: str,
    fallback: str | None,
    include_fallback_block: bool = True,
) -> App:
    (template_dir / "_layout.html").write_text(
        "<!doctype html><html><body>{% block page_root %}{% end %}</body></html>",
        encoding="utf-8",
    )
    fallback_modifier = f" fallback={fallback}" if fallback is not None else ""
    fallback_block = (
        '{% block chart_table %}<section id="sales-chart">fallback-{{ state }}</section>{% end %}'
        if include_fallback_block
        else '<section id="sales-chart">unrelated-{{ state }}</section>'
    )
    (template_dir / "page.html").write_text(
        "{% extends '_layout.html' %}"
        f"{{% block page_root %}}{fallback_block}{{% end %}}"
        f"{{% fragment chart_live enhancement={enhancement}{fallback_modifier} %}}"
        '<section id="sales-chart">live-{{ state }}</section>'
        "{% end %}",
        encoding="utf-8",
    )
    app = App(AppConfig(template_dir=template_dir, skip_contract_checks=True))

    @app.route("/", template="page.html")
    def index() -> Page:
        return Page("page.html", "chart_live", page_block_name="page_root", state="ready")

    return app


def _program(app: App):
    app.freeze()
    program = app._runtime_state.hypermedia_program
    assert program is not None
    return program


@pytest.mark.issue(723)
@pytest.mark.parametrize("capability", [pytest.param("htmx"), pytest.param("sse")])
async def test_valid_declared_fallback_keeps_plain_and_htmx_paths_intact(
    tmp_path, capability: str
) -> None:
    app = _enhancement_app(
        tmp_path,
        enhancement=f'"{capability}"',
        fallback='"chart_table"',
    )

    async with TestClient(app) as client:
        plain = await client.get("/")
        enhanced = await client.fragment("/", target="sales-chart")

    assert plain.status == enhanced.status == 200
    assert_is_full_page(plain)
    assert "fallback-ready" in plain.text
    assert "live-ready" not in plain.text
    assert_no_full_document(enhanced)
    assert "live-ready" in enhanced.text

    program = _program(app)
    node = program.enhancements[0]
    edge = program.enhancement_edges[0]
    assert node.capability == capability
    assert node.fallback == "chart_table"
    assert node.fallback_declared is True
    assert edge.fallback_block_id == stable_identity("block", "page.html", "chart_table")
    assert edge.resolved is True


@pytest.mark.issue(723)
@pytest.mark.parametrize(
    ("enhancement", "fallback", "include_fallback", "expected"),
    [
        ('"future"', '"chart_table"', True, ("future", "chart_table", True, True)),
        ('"sse"', None, True, ("sse", None, False, None)),
        ('"sse"', '"missing"', False, ("sse", "missing", True, False)),
        ("7", '"chart_table"', True, (7, "chart_table", True, True)),
        ('"sse"', "7", True, ("sse", 7, True, None)),
    ],
    ids=(
        "unknown-capability",
        "missing-fallback-declaration",
        "unresolved-fallback-name",
        "non-string-capability",
        "non-string-fallback",
    ),
)
def test_compiler_preserves_each_diagnostic_input_without_guessing(
    tmp_path,
    enhancement: str,
    fallback: str | None,
    include_fallback: bool,
    expected: tuple[object, object, bool, bool | None],
) -> None:
    app = _enhancement_app(
        tmp_path,
        enhancement=enhancement,
        fallback=fallback,
        include_fallback_block=include_fallback,
    )

    program = _program(app)

    assert len(program.enhancements) == 1
    node = program.enhancements[0]
    edge = program.enhancement_edges[0] if program.enhancement_edges else None
    assert (
        node.capability,
        node.fallback,
        node.fallback_declared,
        edge.resolved if edge is not None else None,
    ) == expected
