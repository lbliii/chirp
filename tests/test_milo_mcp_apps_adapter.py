"""Issue #577: frozen Chirp bindings over caller-owned Milo MCP Apps state."""

from __future__ import annotations

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from milo import CLI, MCPAppToolMeta

from chirp import App, ConfigurationError
from chirp.ext.milo import MiloMCPAppBinding, use_milo


def _empty_context() -> dict[str, object]:
    return {}


def _configured_cli(
    *,
    command_name: str = "inspect",
    resource_uri: str = "ui://chirp/inspect",
    aliases: tuple[str, ...] = (),
) -> CLI:
    cli = CLI(name="adapter-test")

    @cli.ui_resource(resource_uri, name="Inspect")
    def inspect_resource() -> str:
        return "<main>caller-owned placeholder</main>"

    @cli.command(
        command_name,
        aliases=aliases,
        ui=MCPAppToolMeta(resource_uri, visibility=("app",)),
    )
    def inspect_command() -> str:
        return "ok"

    return cli


@pytest.mark.issue(577)
class TestMiloMCPAppAdapter:
    def test_freeze_publishes_sorted_frozen_snapshot(self) -> None:
        app = App()
        cli = _configured_cli()
        adapter = use_milo(app, cli, allowlist=("inspect",))

        def context() -> dict[str, str]:
            return {"title": "Inspection"}

        adapter.bind(
            "inspect",
            template="tools.html",
            block="inspect_tool",
            context=context,
        )

        with pytest.raises(RuntimeError, match=r"not available until.*frozen"):
            _ = adapter.bindings

        app.freeze()

        assert adapter.bindings == (
            MiloMCPAppBinding(
                operation_id="inspect",
                resource_uri="ui://chirp/inspect",
                visibility=("app",),
                template="tools.html",
                block="inspect_tool",
                context_provider=context,
            ),
        )
        block_attribute = "block"
        with pytest.raises(FrozenInstanceError):
            setattr(adapter.bindings[0], block_attribute, "other")
        assert not hasattr(adapter.bindings[0], "__dict__")
        assert app._mutable_state.template_declarations[-1].template == "tools.html"
        assert app._mutable_state.template_declarations[-1].blocks == ("inspect_tool",)

    def test_exact_allowlist_requires_every_binding(self) -> None:
        app = App()
        adapter = use_milo(app, _configured_cli(), allowlist=("inspect",))

        with pytest.raises(ConfigurationError, match="missing bindings: inspect"):
            app.freeze()

        adapter.bind(
            "inspect",
            template="tools.html",
            block="inspect_tool",
            context=_empty_context,
        )
        app.freeze()

    def test_binding_outside_allowlist_fails_during_setup(self) -> None:
        app = App()
        adapter = use_milo(app, _configured_cli(), allowlist=("inspect",))

        with pytest.raises(ConfigurationError, match="not in this adapter's exact allowlist"):
            adapter.bind(
                "other",
                template="tools.html",
                block="other_tool",
                context=_empty_context,
            )

    def test_empty_and_duplicate_allowlist_entries_fail_closed(self) -> None:
        app = App()
        cli = _configured_cli()

        with pytest.raises(ConfigurationError, match="at least one canonical dotted"):
            use_milo(app, cli, allowlist=())
        with pytest.raises(ConfigurationError, match="duplicate command IDs"):
            use_milo(app, cli, allowlist=("inspect", "inspect"))

    def test_duplicate_binding_fails_during_setup(self) -> None:
        app = App()
        adapter = use_milo(app, _configured_cli(), allowlist=("inspect",))
        adapter.bind(
            "inspect",
            template="tools.html",
            block="inspect_tool",
            context=_empty_context,
        )

        with pytest.raises(ConfigurationError, match="already has a Chirp MCP App binding"):
            adapter.bind(
                "inspect",
                template="other.html",
                block="other",
                context=_empty_context,
            )

    def test_alias_is_rejected_in_favor_of_canonical_identity(self) -> None:
        app = App()
        adapter = use_milo(
            app,
            _configured_cli(aliases=("show",)),
            allowlist=("show",),
        )
        adapter.bind(
            "show",
            template="tools.html",
            block="inspect_tool",
            context=_empty_context,
        )

        with pytest.raises(ConfigurationError, match="resolves as an alias"):
            app.freeze()

    def test_missing_canonical_command_is_actionable(self) -> None:
        app = App()
        adapter = use_milo(app, _configured_cli(), allowlist=("missing",))
        adapter.bind(
            "missing",
            template="tools.html",
            block="missing_tool",
            context=_empty_context,
        )

        with pytest.raises(ConfigurationError, match="not a registered canonical dotted"):
            app.freeze()

    def test_command_requires_original_ui_metadata(self) -> None:
        app = App()
        cli = CLI(name="adapter-test")

        @cli.command("inspect")
        def inspect_command() -> str:
            return "ok"

        adapter = use_milo(app, cli, allowlist=("inspect",))
        adapter.bind(
            "inspect",
            template="tools.html",
            block="inspect_tool",
            context=_empty_context,
        )

        with pytest.raises(ConfigurationError, match="Attach matching ui=MCPAppToolMeta"):
            app.freeze()

    def test_command_must_be_enabled_for_mcp(self) -> None:
        app = App()
        cli = CLI(name="adapter-test")

        @cli.ui_resource("ui://chirp/inspect")
        def inspect_resource() -> str:
            return "<main></main>"

        @cli.command(
            "inspect",
            surfaces=("cli",),
            ui=MCPAppToolMeta("ui://chirp/inspect"),
        )
        def inspect_command() -> str:
            return "ok"

        adapter = use_milo(app, cli, allowlist=("inspect",))
        adapter.bind(
            "inspect",
            template="tools.html",
            block="inspect_tool",
            context=_empty_context,
        )

        with pytest.raises(ConfigurationError, match="not enabled for the MCP surface"):
            app.freeze()

    def test_nested_and_lazy_canonical_commands_compile_without_resolution(self) -> None:
        app = App()
        cli = CLI(name="adapter-test")
        group = cli.group("work-items")

        @cli.ui_resource("ui://chirp/work-items/create")
        def create_resource() -> str:
            return "<main></main>"

        group.lazy_command(
            "create",
            "example_missing_module:create",
            ui=MCPAppToolMeta("ui://chirp/work-items/create"),
        )
        adapter = use_milo(app, cli, allowlist=("work-items.create",))
        adapter.bind(
            "work-items.create",
            template="work_items.html",
            block="create_tool",
            context=_empty_context,
        )

        app.freeze()

        assert adapter.bindings[0].operation_id == "work-items.create"

    def test_tool_link_requires_matching_ui_resource(self) -> None:
        app = App()
        cli = CLI(name="adapter-test")

        @cli.command("inspect", ui=MCPAppToolMeta("ui://chirp/missing"))
        def inspect_command() -> str:
            return "ok"

        adapter = use_milo(app, cli, allowlist=("inspect",))
        adapter.bind(
            "inspect",
            template="tools.html",
            block="inspect_tool",
            context=_empty_context,
        )

        with pytest.raises(ConfigurationError, match=r"no matching cli\.ui_resource"):
            app.freeze()

    def test_bindings_are_sorted_by_canonical_identity(self) -> None:
        app = App()
        cli = CLI(name="adapter-test")
        for name in ("zeta", "alpha"):
            uri = f"ui://chirp/{name}"

            def resource() -> str:
                return "<main></main>"

            cli.ui_resource(uri, name=name)(resource)

            def command() -> str:
                return "ok"

            cli.command(name, ui=MCPAppToolMeta(uri))(command)

        adapter = use_milo(app, cli, allowlist=("zeta", "alpha"))
        for name in ("zeta", "alpha"):
            adapter.bind(
                name,
                template="tools.html",
                block=f"{name}_tool",
                context=_empty_context,
            )

        app.freeze()

        assert tuple(binding.operation_id for binding in adapter.bindings) == ("alpha", "zeta")

    @pytest.mark.parametrize("target", ["context", "resource"])
    def test_context_and_resource_handlers_are_parameterless(self, target: str) -> None:
        app = App()
        cli = CLI(name="adapter-test")

        if target == "resource":

            @cli.ui_resource("ui://chirp/inspect")
            def inspect_resource(required: str) -> str:
                return required

        else:

            @cli.ui_resource("ui://chirp/inspect")
            def inspect_resource() -> str:
                return "<main></main>"

        @cli.command("inspect", ui=MCPAppToolMeta("ui://chirp/inspect"))
        def inspect_command() -> str:
            return "ok"

        adapter = use_milo(app, cli, allowlist=("inspect",))
        if target == "context":

            def context(required: str) -> dict[str, str]:
                return {"required": required}

        else:
            context = _empty_context

        if target == "context":
            with pytest.raises(ConfigurationError, match=r"context provider.*parameterless"):
                adapter.bind(
                    "inspect",
                    template="tools.html",
                    block="inspect_tool",
                    context=context,  # type: ignore[arg-type]
                )
            return

        adapter.bind(
            "inspect",
            template="tools.html",
            block="inspect_tool",
            context=context,
        )
        with pytest.raises(ConfigurationError, match=r"resource handler.*parameterless"):
            app.freeze()

    def test_binding_is_setup_only_and_milo_cli_remains_caller_owned(self) -> None:
        app = App()
        cli = _configured_cli()
        adapter = use_milo(app, cli, allowlist=("inspect",))
        adapter.bind(
            "inspect",
            template="tools.html",
            block="inspect_tool",
            context=_empty_context,
        )
        commands_before = list(cli.walk_commands())
        resources_before = cli.walk_ui_resources()
        app.freeze()
        original_snapshot = adapter.bindings

        assert list(cli.walk_commands()) == commands_before
        assert cli.walk_ui_resources() == resources_before

        with pytest.raises(RuntimeError, match="Cannot modify the app"):
            adapter.bind(
                "inspect",
                template="other.html",
                block="other",
                context=_empty_context,
            )

        @cli.command("caller-added-later")
        def caller_added_later() -> str:
            return "still mutable"

        assert cli.get_command("caller-added-later") is not None
        assert adapter.bindings is original_snapshot

    def test_use_milo_is_setup_only(self) -> None:
        app = App()
        app.freeze()

        with pytest.raises(RuntimeError, match="Cannot modify the app"):
            use_milo(app, _configured_cli(), allowlist=("inspect",))

    def test_freeze_never_invokes_application_context(self) -> None:
        app = App()
        calls = 0

        def context() -> dict[str, object]:
            nonlocal calls
            calls += 1
            return {}

        adapter = use_milo(app, _configured_cli(), allowlist=("inspect",))
        adapter.bind(
            "inspect",
            template="tools.html",
            block="inspect_tool",
            context=context,
        )

        app.freeze()

        assert calls == 0

    def test_concurrent_freeze_publishes_one_snapshot(self) -> None:
        app = App()
        adapter = use_milo(app, _configured_cli(), allowlist=("inspect",))
        adapter.bind(
            "inspect",
            template="tools.html",
            block="inspect_tool",
            context=_empty_context,
        )

        with ThreadPoolExecutor(max_workers=8) as pool:
            snapshots = list(pool.map(lambda _: (app.freeze(), adapter.bindings)[1], range(32)))

        assert all(snapshot is snapshots[0] for snapshot in snapshots)

    def test_adapter_does_not_use_milo_private_registries(self) -> None:
        source = Path(sys.modules["chirp.ext.milo"].__file__).read_text()
        assert "._commands" not in source
        assert "._ui_resources" not in source
        assert "get_request" not in source
        assert "ContextVar" not in source
        assert "latest_result" not in source


@pytest.mark.issue(577)
def test_ext_module_import_is_lazy_and_missing_milo_error_is_actionable() -> None:
    code = """
import importlib.abc
import sys
import types

class BlockMilo(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "milo" or fullname.startswith("milo."):
            raise ModuleNotFoundError("simulated partial installation", name=fullname)
        return None

sys.meta_path.insert(0, BlockMilo())
import chirp
from chirp.ext import milo as adapter
try:
    adapter._load_milo_cli()
except ImportError as exc:
    print(str(exc))
else:
    raise SystemExit("expected ImportError")

partial = types.ModuleType("milo")
partial.CLI = type("PartialCLI", (), {})
partial.MCPAppToolMeta = object
sys.modules["milo"] = partial
try:
    adapter._load_milo_cli()
except ImportError as exc:
    print(str(exc))
else:
    raise SystemExit("expected partial-install ImportError")
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.count("pip install --force-reinstall bengal-chirp") == 2
