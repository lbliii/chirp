"""Contract surfacing for the MCP legacy-client offramp (#967)."""

from pathlib import Path

import pytest

from chirp import App, AppConfig
from chirp.contracts.rules_mcp_legacy import check_mcp_legacy_offramp
from chirp.contracts.types import Severity
from chirp.tools.events import ToolEventBus
from chirp.tools.registry import compile_tools


@pytest.mark.issue(967)
def test_mcp_legacy_offramp_info_when_tools_registered() -> None:
    registry = compile_tools(
        [("greet", "Greet", lambda name: f"hi {name}")],
        ToolEventBus(),
    )
    issues = check_mcp_legacy_offramp(registry, mcp_path="/mcp")
    assert len(issues) == 1
    assert issues[0].category == "mcp_legacy"
    assert issues[0].severity == Severity.INFO
    assert "2024-11-05" in issues[0].message
    assert "2027-07-28" in issues[0].message
    assert issues[0].route == "/mcp"


@pytest.mark.issue(967)
def test_mcp_legacy_offramp_silent_without_tools() -> None:
    assert check_mcp_legacy_offramp(None) == []
    empty = compile_tools([], ToolEventBus())
    assert check_mcp_legacy_offramp(empty) == []


@pytest.mark.issue(967)
def test_app_check_surfaces_mcp_legacy(tmp_path: Path) -> None:
    from chirp.contracts.checker import check_hypermedia_surface

    app = App(AppConfig(template_dir=tmp_path, skip_contract_checks=True))

    @app.tool("ping", description="Ping")
    def ping() -> str:
        return "pong"

    app.freeze()
    result = check_hypermedia_surface(app)
    issues = [i for i in result.issues if i.category == "mcp_legacy"]
    assert len(issues) == 1
    assert issues[0].severity == Severity.INFO
