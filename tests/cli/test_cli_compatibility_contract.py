"""Black-box compatibility contract across the #571 baseline and #572 migration."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_CONTRACT_DOC = _ROOT / "docs" / "cli-compatibility-contract.md"

_HELP_HEADINGS = {
    (): "chirp — Chirp — A Python web framework for the modern web platform.",
    ("new",): "chirp new - Create a new project",
    ("run",): "chirp run - Start dev or production server",
    ("dev",): "chirp dev - Development server with browser reload on template/CSS changes",
    ("check",): "chirp check - Validate hypermedia contracts",
    ("diff",): "chirp diff - Diff hypermedia contracts against a git base ref",
    ("routes",): "chirp routes - List registered routes",
    ("security-check",): "chirp security-check - Audit app config against OWASP security checklist",
    ("freeze",): "chirp freeze - Render routes to static HTML files",
    ("makemigrations",): "chirp makemigrations - Auto-generate schema migration from SQL diff",
    ("migrate",): "chirp migrate - Apply pending schema migrations (one-shot deploy job)",
    ("shapes-codegen",): "chirp shapes-codegen - Suggest @shape decorators and audit Shape drift",
    ("skill",): "chirp skill - Skill authoring and publish-oracle gates",
    (
        "skill",
        "publish",
    ): "chirp skill publish - Run check + freeze + smoke and emit a publish receipt",
}

# Top-level command names only (root help order). Nested groups use _NESTED_*.
_POSITIONALS = {
    "new": ("name",),
    "run": ("app",),
    "dev": ("app",),
    "check": ("app",),
    "diff": ("app",),
    "routes": ("app",),
    "security-check": ("app",),
    "freeze": ("app", "output"),
    "makemigrations": (),
    "migrate": (),
    "shapes-codegen": ("path",),
    "skill": (),
}

_NESTED_POSITIONALS = {
    ("skill", "publish"): ("app",),
}

_FLAGS = {
    "global": ("--help", "--version"),
    "new": ("--minimal", "--stream", "--sse", "--shell", "--ai", "--with-chirpui"),
    "run": (
        "--host",
        "--port",
        "--production",
        "--workers",
        "--metrics",
        "--rate-limit",
        "--queue",
        "--sentry-dsn",
    ),
    "dev": (
        "--host",
        "--port",
        "--production",
        "--workers",
        "--metrics",
        "--rate-limit",
        "--queue",
        "--sentry-dsn",
    ),
    "check": (
        "--warnings-as-errors",
        "--coverage",
        "--deploy",
        "--json",
        "--baseline",
        "--include-info",
    ),
    "diff": ("--base", "--json", "--warnings-as-errors", "--deploy", "--include-info"),
    "routes": (),
    "security-check": (),
    "freeze": ("--exclude",),
    "makemigrations": ("--db", "--schema", "--migrations-dir"),
    "migrate": ("--db", "--migrations-dir"),
    "shapes-codegen": ("--dry-run", "--audit", "--migrations"),
    "skill.publish": (
        "--corpus",
        "--fixture",
        "--warnings-as-errors",
        "--json",
    ),
}


def _run_cli(
    *args: str,
    cwd: Path = _ROOT,
    python_paths: tuple[Path, ...] = (),
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["COLUMNS"] = "80"
    env["NO_COLOR"] = "1"
    paths = [str(_ROOT / "src"), *(str(path) for path in python_paths)]
    if env.get("PYTHONPATH"):
        paths.append(env["PYTHONPATH"])
    if paths:
        env["PYTHONPATH"] = os.pathsep.join(paths)
    return subprocess.run(
        [sys.executable, "-m", "chirp.cli", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.issue(572)
@pytest.mark.parametrize(("command", "expected"), _HELP_HEADINGS.items())
def test_milo_help_preserves_command_meaning(command: tuple[str, ...], expected: str) -> None:
    result = _run_cli(*command, "--help")
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout.splitlines()[0] == expected
    if command in _NESTED_POSITIONALS:
        for positional in _NESTED_POSITIONALS[command]:
            assert f"  {positional} {positional}" in result.stdout
    elif command:
        for positional in _POSITIONALS[command[0]]:
            assert f"  {positional} {positional}" in result.stdout
    else:
        offsets = [result.stdout.index(f"  {name}") for name in _POSITIONALS]
        assert offsets == sorted(offsets)


@pytest.mark.issue(571)
@pytest.mark.parametrize("command", _FLAGS)
def test_help_and_contract_doc_inventory_every_flag(command: str) -> None:
    if command == "global":
        args: tuple[str, ...] = ()
    elif "." in command:
        args = tuple(command.split("."))
    else:
        args = (command,)
    result = _run_cli(*args, "--help")
    assert result.returncode == 0
    contract = _CONTRACT_DOC.read_text(encoding="utf-8")
    for flag in _FLAGS[command]:
        assert flag in result.stdout, f"{command} help omitted {flag}"
        assert flag in contract, f"compatibility contract omitted {command} {flag}"


@pytest.mark.issue(571)
def test_no_command_and_version_are_stdout_exit_zero() -> None:
    no_command = _run_cli()
    assert no_command.returncode == 0
    assert no_command.stderr == ""
    assert no_command.stdout.startswith(_HELP_HEADINGS[()] + "\n")
    assert "  new " in no_command.stdout
    assert "  shapes-codegen " in no_command.stdout
    assert "  skill " in no_command.stdout
    version = _run_cli("--version")
    assert version.returncode == 0
    assert version.stderr == ""
    assert version.stdout.startswith("chirp ")
    assert "kida" in version.stdout
    assert "bengal-pounce" in version.stdout
    assert "Python" in version.stdout


@pytest.mark.issue(571)
@pytest.mark.parametrize("command", _HELP_HEADINGS)
def test_unknown_option_is_stderr_exit_two(command: tuple[str, ...]) -> None:
    result = _run_cli(*command, "--definitely-not-a-chirp-option")
    assert result.returncode == 2
    assert result.stdout == ""
    assert "usage:" in result.stderr
    assert "error:" in result.stderr


@pytest.mark.issue(571)
@pytest.mark.parametrize(
    "args",
    [
        ("run", "missing_cli_contract_app:app"),
        ("dev", "missing_cli_contract_app:app"),
        ("check", "missing_cli_contract_app:app"),
        ("routes", "missing_cli_contract_app:app"),
        ("freeze", "missing_cli_contract_app:app", "dist"),
        ("shapes-codegen", "missing_cli_contract_app:app", "--audit"),
        ("diff", "missing_cli_contract_app:app", "--base", "HEAD"),
    ],
)
def test_app_resolution_failure_is_stderr_exit_one(args: tuple[str, ...]) -> None:
    result = _run_cli(*args)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith("Error:")
    assert "missing_cli_contract_app" in result.stderr


@pytest.mark.issue(571)
def test_security_check_resolution_failure_currently_uses_traceback_stderr() -> None:
    result = _run_cli("security-check", "missing_cli_contract_app:app")
    assert result.returncode == 1
    assert result.stdout == ""
    assert "Traceback" in result.stderr
    assert "ModuleNotFoundError" in result.stderr
    assert "missing_cli_contract_app" in result.stderr


def _write_contract_app(path: Path, *, warning: bool) -> None:
    methods = ', methods=["POST"]' if warning else ""
    path.joinpath("compat_app.py").write_text(
        "from chirp import App, AppConfig\n"
        "app = App(AppConfig(template_dir=None, static_dir=None))\n"
        f'@app.route("/"{methods})\n'
        "def index():\n"
        '    return "ok"\n',
        encoding="utf-8",
    )


@pytest.mark.issue(571)
def test_check_json_is_machine_parseable_stdout(tmp_path: Path) -> None:
    _write_contract_app(tmp_path, warning=False)
    result = _run_cli(
        "check",
        "compat_app:app",
        "--json",
        cwd=tmp_path,
        python_paths=(tmp_path,),
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    assert set(payload) == {"ok", "routes_checked", "templates_scanned", "issues"}
    assert payload["ok"] is True
    assert isinstance(payload["issues"], list)
    assert isinstance(payload["routes_checked"], int)


@pytest.mark.issue(571)
def test_warnings_as_errors_changes_only_exit_policy(tmp_path: Path) -> None:
    _write_contract_app(tmp_path, warning=True)
    plain = _run_cli("check", "compat_app:app", cwd=tmp_path, python_paths=(tmp_path,))
    strict = _run_cli(
        "check",
        "compat_app:app",
        "--warnings-as-errors",
        cwd=tmp_path,
        python_paths=(tmp_path,),
    )
    assert plain.returncode == 0
    assert strict.returncode == 1
    assert "warning" in plain.stdout.lower()
    assert "warning" in strict.stdout.lower()
    assert plain.stderr == strict.stderr == ""


@pytest.mark.issue(571)
def test_parser_and_help_keep_command_handlers_lazy() -> None:
    handlers = [
        "_milo_handlers",
        "_new",
        "_run",
        "_check",
        "_diff",
        "_routes",
        "_security_check",
        "_freeze",
        "_makemigrations",
        "_migrate",
        "_shapes_codegen",
        "_version",
    ]
    script = (
        "import contextlib, io, json, sys; import chirp.cli as cli; "
        "sink = io.StringIO(); "
        "ctx = contextlib.redirect_stdout(sink); ctx.__enter__(); "
        "\ntry:\n cli.main(['--help'])\nexcept SystemExit:\n pass\nfinally:\n ctx.__exit__(None, None, None)\n"
        f"print(json.dumps([name for name in {handlers!r} "
        "if 'chirp.cli.' + name in sys.modules]))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []


@pytest.mark.issue(571)
def test_version_imports_only_its_lazy_report_module() -> None:
    handlers = [
        "_new",
        "_run",
        "_check",
        "_diff",
        "_routes",
        "_security_check",
        "_freeze",
        "_makemigrations",
        "_migrate",
        "_shapes_codegen",
    ]
    script = (
        "import contextlib, io, json, sys; import chirp.cli as cli; "
        "sink = io.StringIO(); ctx = contextlib.redirect_stdout(sink); ctx.__enter__(); "
        "\ntry:\n cli.main(['--version'])\nexcept SystemExit:\n pass\nfinally:\n ctx.__exit__(None, None, None)\n"
        f"print(json.dumps({{'version': 'chirp.cli._version' in sys.modules, "
        f"'handlers': [name for name in {handlers!r} "
        "if 'chirp.cli.' + name in sys.modules]}))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"version": True, "handlers": []}
