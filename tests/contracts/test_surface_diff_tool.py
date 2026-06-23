"""MCP ``chirp_surface_diff`` tool for agent consumption (issue #344)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from chirp.contracts import register_surface_diff_tool
from chirp.contracts.surface_diff import collect_surface_diff


@pytest.mark.issue(344)
def test_register_surface_diff_tool_lists_in_registry() -> None:
    pytest.importorskip("chirp_ui")
    from chirp import App, AppConfig

    app = App(AppConfig())
    register_surface_diff_tool(app, "examples.chirpui.forum_shell.app:app")
    app.freeze()

    names = [t["name"] for t in app.tools.list_tools()]
    assert "chirp_surface_diff" in names


@pytest.mark.issue(344)
def test_chirp_surface_diff_tool_returns_json_payload() -> None:
    pytest.importorskip("chirp_ui")
    import importlib.util
    import sys
    from pathlib import Path

    from chirp import App, AppConfig

    app_path = Path(__file__).resolve().parents[2] / "examples" / "chirpui" / "forum_shell" / "app.py"
    spec = importlib.util.spec_from_file_location("forum_shell_app", app_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["forum_shell_app"] = module
    spec.loader.exec_module(module)
    forum_app = module.app
    forum_app.freeze()

    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],  # noqa: S607
        cwd=Path(__file__).resolve().parents[2],
        text=True,
    ).strip()

    _, payload = collect_surface_diff(
        forum_app,
        "examples.chirpui.forum_shell.app:app",
        head,
    )
    assert payload["base_ref"] == head
    assert "baseline" in payload
    assert "current" in payload
    assert "diff" in payload
    assert "summary_lines" in payload


@pytest.mark.issue(344)
@pytest.mark.asyncio
async def test_chirp_surface_diff_tool_dispatch() -> None:
    pytest.importorskip("chirp_ui")
    from chirp import App, AppConfig

    app = App(AppConfig())
    register_surface_diff_tool(app, "examples.chirpui.forum_shell.app:app")
    app.freeze()

    mock_payload = {
        "base_ref": "origin/main",
        "app_import": "examples.chirpui.forum_shell.app:app",
        "baseline": {"issues": []},
        "current": {"issues": []},
        "diff": {"added": [], "removed": []},
        "summary_lines": ["Hypermedia surface change:", "  (no issue changes)"],
    }
    with patch(
        "chirp.contracts.surface_diff.collect_surface_diff",
        return_value=(type("D", (), {"has_changes": False})(), mock_payload),
    ):
        result = await app.tools.call_tool(
            "chirp_surface_diff",
            {"base_ref": "origin/main"},
        )
    assert result["base_ref"] == "origin/main"
    assert result["diff"]["added"] == []


@pytest.mark.issue(344)
def test_chirp_surface_diff_schema_has_base_ref_param() -> None:
    from chirp import App, AppConfig

    app = App(AppConfig())
    register_surface_diff_tool(app, "examples.standalone.tools.app:app")
    app.freeze()
    tool = app.tools.get("chirp_surface_diff")
    assert tool is not None
    props = tool.schema.get("properties", {})
    assert "base_ref" in props
