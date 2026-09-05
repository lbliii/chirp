"""Offline sensitivity proof for first-party private API classifications (#1053)."""

import json
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.private_api_ratchet import (
    DEFAULT_LEDGER,
    check_repository,
    main,
    scan_source,
    validate_ledger,
)

pytestmark = pytest.mark.issue(1053)


def symbols(source: str, hints=None) -> list[str]:
    return [row.symbol for row in scan_source(source, "app.py", hints)]


@pytest.mark.parametrize(
    "source",
    [
        "from chirp import App as Framework\napp = Framework()\nalias = app\nalias._runtime",
        "import chirp as framework\napp = framework.App()\napp._runtime",
        "from chirp.app import App\ndef run(app: App):\n    app._runtime",
        "from chirp import App\ndef build() -> App: ...\napp = build()\napp._runtime",
        "from chirp import App\ndef run(app: 'App | None'):\n    app._runtime",
    ],
)
def test_constructor_parameter_factory_and_alias_provenance(source: str) -> None:
    assert symbols(source)[0].endswith("App._runtime")


def test_request_annotations_and_literal_dynamic_access() -> None:
    assert (
        symbols(
            "from chirp import Request\ndef run(request: Request):\n"
            "    getattr(request, '_cache')\n    setattr(request, '_cache', {})\n"
            "    hasattr(request, '_cache')"
        )
        == ["chirp.Request._cache"] * 3
    )


def test_private_import_alias_and_private_module_import() -> None:
    assert symbols("from chirp.middleware.auth import _user_var as current") == [
        "chirp.middleware.auth._user_var"
    ]
    assert symbols("import chirp._internal.asgi as asgi") == ["chirp._internal.asgi"]


@pytest.mark.parametrize(
    "tail",
    [
        "@chirp._decorate\ndef f(): pass",
        "def f(x=chirp._default): pass",
        "def f(*, x=chirp._default): pass",
        "def f(x: chirp._Type) -> chirp._Type: pass",
        "class C(chirp._Base): pass",
        "class C(metaclass=chirp._Meta): pass",
    ],
)
def test_definition_headers_cannot_hide_private_access(tail: str) -> None:
    assert symbols("import chirp\n" + tail)


def test_parameter_shadow_does_not_hide_outer_default_or_taint_local_body() -> None:
    assert symbols("import chirp\ndef f(chirp=chirp._default):\n    chirp._local") == [
        "chirp._default"
    ]


def test_application_internals_and_non_chirp_names_are_not_flagged() -> None:
    assert (
        symbols(
            "from chirp import App\nfrom application import Request\n"
            "class Services:\n    def load(self):\n        return self._database\n"
            "def run(request: Request, app):\n    request._cache\n    app._runtime\n"
            "app = App()\napp = object()\napp._local"
        )
        == []
    )


def test_receiver_hint_catches_future_private_fields_without_flagging_local_holder() -> None:
    hints = [{"scope": "Proxy", "receiver": "self._app", "origin": "chirp.App"}]
    assert symbols(
        "class Proxy:\n    def run(self):\n        self._app._new_field\n"
        "        self._local_method()",
        hints,
    ) == ["chirp.App._new_field"]


def test_module_patch_is_a_reviewable_compatibility_access() -> None:
    assert symbols(
        "import chirp.server.production as production\n"
        "vars(production)['run_production_server'] = replacement"
    ) == ["chirp.server.production.run_production_server"]


def _tracked_source(root: Path, path: str, source: str) -> None:
    file = root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(source)
    git = shutil.which("git")
    assert git is not None
    subprocess.run([git, "init", "-q", str(root)], check=True)
    subprocess.run([git, "add", path], cwd=root, check=True)


def test_ratchet_rejects_new_reference_and_duplicate_occurrence(tmp_path: Path) -> None:
    source = "from chirp import App\napp = App()\napp._runtime\n"
    _tracked_source(tmp_path, "app.py", source)
    finding = scan_source(source, "app.py")[0]
    baseline = {"findings": [{"key": finding.key, "count": 1}]}
    assert check_repository(tmp_path, baseline) == []
    (tmp_path / "app.py").write_text(source + "app._runtime\napp._new_state\n")
    errors = check_repository(tmp_path, baseline)
    assert any("chirp.App._new_state" in error for error in errors)
    assert any("chirp.App._runtime" in error for error in errors)
    assert all("owner, rationale, and follow-up" in error for error in errors)


def test_test_inspection_is_allowed_but_production_copy_requires_classification(
    tmp_path: Path,
) -> None:
    source = "from chirp import App\nApp()._runtime\n"
    # Attribute on a constructor call is covered just like an assigned alias.
    _tracked_source(tmp_path, "tests/test_app.py", source)
    assert check_repository(tmp_path, {"findings": []}) == []
    _tracked_source(tmp_path, "service.py", source)
    assert check_repository(tmp_path, {"findings": []})


def test_fingerprints_ignore_line_moves_but_keep_operation_scope() -> None:
    source = "from chirp import App\ndef run(app: App):\n    app._runtime\n"
    original = scan_source(source, "app.py")[0]
    shifted = scan_source("\n\n" + source, "app.py")[0]
    assert original.key == shifted.key
    assert original.line != shifted.line
    assert original.key != scan_source(source.replace("run", "other"), "app.py")[0].key


def test_committed_ledger_has_five_source_pins_and_complete_ownership() -> None:
    ledger = json.loads(DEFAULT_LEDGER.read_text())
    assert validate_ledger(ledger) == []
    assert all(repo["manual_decisions"] for repo in ledger["repositories"].values())
    bad = deepcopy(ledger)
    bad["repositories"]["pidge"]["findings"][0].pop("owner")
    assert any("missing owner" in error for error in validate_ledger(bad))
    bad = deepcopy(ledger)
    bad["repositories"]["pidge"]["revision"] = "main"
    assert validate_ledger(bad)


def test_cli_matrix_and_invalid_repository_are_explicit(capsys) -> None:
    assert main(["--matrix"]) == 0
    assert len(json.loads(capsys.readouterr().out)["include"]) == 5
    assert main(["--repo", "unknown=/tmp"]) == 1
    assert "Unknown repository mapping" in capsys.readouterr().err


def test_rebinding_import_to_application_type_removes_chirp_provenance() -> None:
    assert (
        symbols("from chirp import App\nfrom application import App\napp = App()\napp._local") == []
    )


def test_stale_receiver_scope_fails_instead_of_silently_losing_coverage() -> None:
    with pytest.raises(ValueError, match="scope 'old_name' no longer exists"):
        symbols(
            "def renamed(app): app._runtime",
            [{"scope": "old_name", "receiver": "app", "origin": "chirp.App"}],
        )


def test_stale_receiver_file_fails_instead_of_silently_losing_coverage(tmp_path: Path) -> None:
    _tracked_source(tmp_path, "new.py", "pass")
    with pytest.raises(ValueError, match=r"receiver file 'old\.py' is missing"):
        check_repository(tmp_path, {"receivers": [{"path": "old.py"}], "findings": []})


@pytest.mark.parametrize(
    "mutation", ["classification", "source", "count", "test-only", "duplicate"]
)
def test_invalid_classification_cannot_be_used_as_allowance(mutation: str) -> None:
    ledger = json.loads(DEFAULT_LEDGER.read_text())
    repo = ledger["repositories"]["pidge"]
    finding = repo["findings"][0]
    if mutation == "duplicate":
        repo["findings"].append(deepcopy(finding))
    elif mutation == "test-only":
        finding["classification"] = "test-only"
    elif mutation == "count":
        finding["count"] = 0
    else:
        finding[mutation] = "unreviewed"
    assert validate_ledger(ledger)


def test_manual_shims_and_receiver_provenance_require_reviewed_evidence() -> None:
    ledger = json.loads(DEFAULT_LEDGER.read_text())
    ledger["repositories"]["pidge"]["manual_decisions"][0].pop("follow_up")
    ledger["repositories"]["elbysodic"]["receivers"][0].pop("evidence")
    errors = validate_ledger(ledger)
    assert any("manual decisions require" in error for error in errors)
    assert any("receiver hints require" in error for error in errors)
