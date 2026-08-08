"""Milo ownership and schema-drift proof for Chirp issue #572."""

from __future__ import annotations

import importlib
import json
import sys
import tomllib
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from milo import function_to_schema, generate_llms_txt
from milo.testing import MCPClient

from chirp import App, AppConfig
from chirp.cli import _build_cli
from chirp.contracts import CheckResult, ContractDiff, ContractIssue, Severity

_ROOT = Path(__file__).resolve().parents[2]


def test_milo_is_a_direct_bounded_runtime_dependency() -> None:
    project = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert "milo-cli>=0.4.1,<0.5" in project["dependencies"]


def test_packaged_entrypoint_uses_milo_without_argparse_registration() -> None:
    source = (_ROOT / "src" / "chirp" / "cli" / "__init__.py").read_text(encoding="utf-8")

    assert 'chirp = "chirp.cli:main"' in (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "from milo import CLI" in source
    assert "lazy_command(" in source
    assert "import argparse" not in source
    assert "add_parser(" not in source
    assert "add_argument(" not in source


def test_precomputed_schemas_match_typed_lazy_handlers() -> None:
    cli = _build_cli()

    for path, command in cli.walk_commands():
        module_name, _, attribute = command.import_path.rpartition(":")
        handler = getattr(importlib.import_module(module_name), attribute)
        assert command.schema == function_to_schema(handler), path


@pytest.mark.issue(573)
def test_agent_surfaces_use_an_explicit_read_only_allowlist() -> None:
    cli = _build_cli()
    exposed = {"check", "diff", "routes"}

    assert len(cli.commands) == 11
    assert "skill" in cli.groups
    assert set(cli.groups["skill"].commands) == {"publish"}
    assert cli.groups["skill"].commands["publish"].surfaces == ("cli",)
    assert {
        name for name, command in cli.commands.items() if command.surfaces != ("cli",)
    } == exposed
    assert all(cli.commands[name].surfaces == ("cli", "mcp", "llms") for name in exposed)
    assert all(
        cli.commands[name].annotations == {"readOnlyHint": True, "openWorldHint": True}
        for name in exposed
    )
    assert {tool.name for tool in MCPClient(cli).list_tools()} == exposed
    llms = generate_llms_txt(cli)
    assert all(f"**{name}**" in llms for name in exposed)
    assert all(f"**{name}**" not in llms for name in set(cli.commands) - exposed)


def test_invocation_local_registries_do_not_share_parser_state() -> None:
    def parse_check(_: int) -> tuple[str, bool]:
        parser = _build_cli().build_parser()
        parsed = parser.parse_args(["check", "myapp:app", "--json"])
        return parsed.app, parsed.json

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(parse_check, range(32)))

    assert results == [("myapp:app", True)] * 32


def _register_agent_test_app(monkeypatch: pytest.MonkeyPatch) -> str:
    app = App(AppConfig(template_dir=None, static_dir=None))

    @app.route("/", name="home")
    def home() -> str:
        return "ok"

    module = types.ModuleType("_milo_agent_test_app")
    module.app = app
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return f"{module.__name__}:app"


@pytest.mark.issue(573)
def test_check_and_routes_share_structured_programmatic_and_mcp_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_import = _register_agent_test_app(monkeypatch)
    cli = _build_cli()

    routes = cli.call("routes", app=app_import)
    called_routes = MCPClient(cli).call("routes", app=app_import)
    called_check = MCPClient(cli).call("check", app=app_import, coverage=True)
    invoked_routes = cli.invoke(["routes", app_import, "--format", "json"])

    assert routes == called_routes.structured
    assert routes["app_import"] == app_import
    assert {
        "methods": ["GET"],
        "path": "/",
        "handler": "home (home)",
        "name": "home",
        "query_media_types": [],
    } in routes["routes"]
    assert called_routes.is_error is False
    assert called_check.is_error is False
    assert called_check.structured["ok"] is True
    assert "coverage" in called_check.structured
    assert invoked_routes.exit_code == 0
    assert json.loads(invoked_routes.output) == routes


@pytest.mark.issue(573)
def test_diff_returns_the_existing_stable_payload_across_agent_surfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_import = _register_agent_test_app(monkeypatch)
    payload = {
        "base_ref": "HEAD~1",
        "app_import": app_import,
        "baseline": {"issues": []},
        "current": {"issues": []},
        "diff": {"added": [], "removed": [], "coverage": []},
        "summary_lines": ["Hypermedia surface change:", "  (no issue changes)"],
    }
    monkeypatch.setattr(
        "chirp.cli._diff.collect_surface_diff",
        lambda *args, **kwargs: (ContractDiff(added=(), removed=()), payload),
    )
    cli = _build_cli()

    programmatic = cli.call("diff", app=app_import, base="HEAD~1")
    called = MCPClient(cli).call("diff", app=app_import, base="HEAD~1")

    assert programmatic == payload
    assert called.is_error is False
    assert called.structured == payload


@pytest.mark.issue(573)
def test_check_mcp_preserves_finding_and_coverage_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_import = _register_agent_test_app(monkeypatch)
    result = CheckResult(
        issues=[
            ContractIssue(
                severity=Severity.ERROR,
                category="fragment_target",
                message="Missing target",
                template="pages/index.html",
                route="home",
                details="Register #results before rendering.",
            )
        ],
        routes_checked=3,
        templates_scanned=2,
    )
    payload = {
        "ok": False,
        "routes_checked": 3,
        "templates_scanned": 2,
        "issues": [
            {
                "severity": "error",
                "category": "fragment_target",
                "message": "Missing target",
                "template": "pages/index.html",
                "route": "home",
                "details": "Register #results before rendering.",
            }
        ],
        "coverage": {"fragment_targets_registered": 0},
    }
    monkeypatch.setattr(
        "chirp.cli._check.collect_check_json",
        lambda *args, **kwargs: (result, payload),
    )

    called = MCPClient(_build_cli()).call("check", app=app_import, coverage=True)

    assert called.is_error is False
    assert called.structured == payload


@pytest.mark.issue(573)
def test_agent_resolution_failure_is_structured_and_repairable() -> None:
    called = MCPClient(_build_cli()).call("routes", app="missing_agent_app:app")

    assert called.is_error is False
    assert called.structured == {
        "ok": False,
        "error": {
            "code": "CHIRP_APP_RESOLUTION",
            "message": "No module named 'missing_agent_app'",
            "app_import": "missing_agent_app:app",
            "suggestion": (
                "Use module:attribute and ensure it resolves to a Chirp App or factory."
            ),
        },
    }


@pytest.mark.issue(573)
def test_concurrent_agent_route_inspection_reads_one_frozen_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_import = _register_agent_test_app(monkeypatch)
    cli = _build_cli()
    expected = cli.call("routes", app=app_import)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: cli.call("routes", app=app_import), range(32)))

    assert results == [expected] * 32
