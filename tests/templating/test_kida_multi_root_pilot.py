"""Consumer-owned proof for Kida's explicit multi-root inspection contract."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from kida import Environment, FileSystemLoader, PrefixLoader

from chirp.templating.kida_adapter import KidaAdapter

_PILOT_ENV = "CHIRP_KIDA_MULTI_ROOT_PILOT"

try:
    from kida.inspection import TemplateRoot, diagnose_roots, inspect_components
except ModuleNotFoundError as exc:
    if exc.name != "kida.inspection" or os.environ.get(_PILOT_ENV) == "1":
        raise
    pytest.skip(
        "Kida's explicit multi-root inspection API is not released yet",
        allow_module_level=True,
    )

_FIXTURE = Path(__file__).parent / "fixtures" / "kida_multi_root"
_CHIRP_ROOT = _FIXTURE / "chirp"
_APP_ROOT = _FIXTURE / "app"


def _roots() -> tuple[TemplateRoot, TemplateRoot]:
    return (
        TemplateRoot("chirp", _CHIRP_ROOT),
        TemplateRoot("app", _APP_ROOT),
    )


def _environment() -> Environment:
    return Environment(
        loader=PrefixLoader(
            {
                "chirp": FileSystemLoader(_CHIRP_ROOT),
                "app": FileSystemLoader(_APP_ROOT),
            }
        ),
        bytecode_cache=False,
    )


@pytest.mark.issue(860)
def test_explicit_roots_work_through_chirp_without_chirp_ui() -> None:
    if os.environ.get(_PILOT_ENV) == "1":
        assert importlib.util.find_spec("chirp_ui") is None

    command = [
        sys.executable,
        "-m",
        "kida",
        "check",
        "--root",
        f"chirp={_CHIRP_ROOT}",
        "--root",
        f"app={_APP_ROOT}",
        "--validate-calls",
        "--format",
        "json",
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["diagnostics"] == []

    environment = _environment()
    adapter = KidaAdapter(environment)
    rendered = adapter.render_template("app/page.html", {})
    assert '<article class="card">Inbox</article>' in rendered

    forward = inspect_components(_roots(), environment=environment)
    reverse = inspect_components(tuple(reversed(_roots())), environment=environment)

    assert forward == reverse
    assert forward.partial is False
    assert forward.diagnostics == ()
    assert [
        (record.owner, record.template, record.metadata.name) for record in forward.components
    ] == [
        ("app", "app/components.html", "notice"),
        ("chirp", "chirp/card.html", "card"),
    ]
    assert [record.source_path for record in forward.components] == [
        str((_APP_ROOT / "components.html").resolve()),
        str((_CHIRP_ROOT / "card.html").resolve()),
    ]
    assert (_CHIRP_ROOT / "card.css").is_file()


@pytest.mark.issue(860)
def test_explicit_root_failures_keep_actionable_ownership(tmp_path: Path) -> None:
    duplicate = diagnose_roots(
        (
            TemplateRoot("app", _APP_ROOT),
            TemplateRoot("app", _CHIRP_ROOT),
        )
    )
    missing_path = tmp_path / "missing"
    missing = diagnose_roots((TemplateRoot("missing", missing_path),))

    malformed_root = tmp_path / "malformed"
    malformed_root.mkdir()
    malformed_path = malformed_root / "broken.html"
    malformed_path.write_text("{% def broken( %}", encoding="utf-8")
    malformed = diagnose_roots((TemplateRoot("broken", malformed_root),))

    assert duplicate.partial is True
    assert [diagnostic.code for diagnostic in duplicate.diagnostics] == ["K-TPL-005"]
    assert "duplicate template root namespace 'app'" in duplicate.diagnostics[0].message

    assert missing.partial is True
    assert [diagnostic.code for diagnostic in missing.diagnostics] == ["K-TPL-005"]
    assert dict(missing.diagnostics[0].metadata) == {
        "owner": "missing",
        "source_path": str(missing_path.resolve()),
    }

    assert malformed.partial is True
    assert len(malformed.diagnostics) == 1
    assert malformed.diagnostics[0].span.path == "broken/broken.html"
    assert dict(malformed.diagnostics[0].metadata) == {
        "owner": "broken",
        "source_path": str(malformed_path),
    }
