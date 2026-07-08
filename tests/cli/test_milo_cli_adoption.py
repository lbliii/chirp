"""Milo ownership and schema-drift proof for Chirp issue #572."""

from __future__ import annotations

import importlib
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from milo import function_to_schema, generate_llms_txt
from milo.testing import MCPClient

from chirp.cli import _build_cli

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

    for name, command in cli.commands.items():
        module_name, _, attribute = command.import_path.rpartition(":")
        handler = getattr(importlib.import_module(module_name), attribute)
        assert command.schema == function_to_schema(handler), name


def test_current_command_tree_is_deny_by_default_for_agent_surfaces() -> None:
    cli = _build_cli()

    assert len(cli.commands) == 11
    assert all(command.surfaces == ("cli",) for command in cli.commands.values())
    assert MCPClient(cli).list_tools() == []
    llms = generate_llms_txt(cli)
    assert all(f"**{name}**" not in llms for name in cli.commands)


def test_invocation_local_registries_do_not_share_parser_state() -> None:
    def parse_check(_: int) -> tuple[str, bool]:
        parser = _build_cli().build_parser()
        parsed = parser.parse_args(["check", "myapp:app", "--json"])
        return parsed.app, parsed.json

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(parse_check, range(32)))

    assert results == [("myapp:app", True)] * 32
