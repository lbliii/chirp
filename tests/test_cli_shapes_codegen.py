"""Integration tests for ``chirp shapes-codegen`` (chirp.cli._shapes_codegen).

Two modes, both proven here:

* **Ingest + emit (default / ``--dry-run``):** a temp module with a known frozen
  dataclass sitting near an explicit named-column ``SELECT`` literal must produce
  a ``@shape("SELECT ...")`` suggestion above that class, and write nothing to
  disk.
* **Audit (``--audit``):** loading an app whose ``surface_contracts`` registry
  names a Shape that is not registered must report the drift and exit non-zero; a
  clean registry must exit 0.

All names are NEUTRAL public examples (``Board`` / ``BoardView`` / ``Card`` /
``Member``) per the Public-Safe filter. ``resolve_app`` is monkeypatched at its
source module (``chirp.cli._resolve``) so the audit runs against an in-test fake
app without importing a real module.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from chirp.cli._shapes_codegen import run_shapes_codegen
from chirp.data import register_shape, shape

# A module whose dataclass fields are a SUPERSET of an explicit-column SELECT's
# output columns -> the ingest step must pair them and suggest @shape. The SELECT
# lives as a module-level string literal near the dataclass (the documented
# ingest heuristic).
_MODULE_WITH_PAIR = """\
from dataclasses import dataclass

BOARD_SQL = "SELECT id, title FROM boards WHERE id = :id"


@dataclass(frozen=True, slots=True)
class BoardView:
    id: int
    title: str
"""

# A module whose dataclass is ALREADY @shape-decorated -> incremental skip (no
# suggestion).
_MODULE_ALREADY_SHAPED = """\
from dataclasses import dataclass
from chirp.data import shape


@shape("SELECT id, title FROM boards")
@dataclass(frozen=True, slots=True)
class BoardView:
    id: int
    title: str
"""


def _ingest_args(path: str) -> SimpleNamespace:
    return SimpleNamespace(path=path, dry_run=True, audit=False, migrations_dir="migrations")


def _audit_args(path: str) -> SimpleNamespace:
    return SimpleNamespace(path=path, dry_run=False, audit=True, migrations_dir="migrations")


# ---------------------------------------------------------------------------
# Ingest + emit (dry-run)
# ---------------------------------------------------------------------------


class TestShapesCodegenDryRun:
    def test_dry_run_emits_shape_for_dataclass_and_select(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A dataclass paired with a named-column SELECT emits a @shape suggestion."""
        module = tmp_path / "models.py"
        module.write_text(_MODULE_WITH_PAIR, encoding="utf-8")
        before = module.read_text(encoding="utf-8")

        run_shapes_codegen(_ingest_args(str(module)))

        out = capsys.readouterr().out
        assert "@shape(" in out
        assert "SELECT id, title FROM boards WHERE id = :id" in out
        assert "BoardView" in out
        # Dry-run: the source file is untouched.
        assert module.read_text(encoding="utf-8") == before
        assert "no files written" in out

    def test_dry_run_skips_already_shaped_dataclass(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Incremental: a class already carrying @shape is not re-suggested."""
        module = tmp_path / "models.py"
        module.write_text(_MODULE_ALREADY_SHAPED, encoding="utf-8")

        run_shapes_codegen(_ingest_args(str(module)))

        out = capsys.readouterr().out
        assert "No unannotated dataclass/SELECT pairs found." in out

    def test_dry_run_scans_a_directory(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A directory PATH walks its .py files for pairs."""
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "models.py").write_text(_MODULE_WITH_PAIR, encoding="utf-8")

        run_shapes_codegen(_ingest_args(str(tmp_path)))

        out = capsys.readouterr().out
        assert "@shape(" in out
        assert "BoardView" in out

    def test_dry_run_no_pairs_reports_cleanly(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A dataclass with no nearby SELECT yields no suggestion."""
        module = tmp_path / "models.py"
        module.write_text(
            "from dataclasses import dataclass\n\n\n"
            "@dataclass(frozen=True, slots=True)\n"
            "class Card:\n"
            "    id: int\n"
            "    label: str\n",
            encoding="utf-8",
        )

        run_shapes_codegen(_ingest_args(str(module)))

        out = capsys.readouterr().out
        assert "No unannotated dataclass/SELECT pairs found." in out

    def test_select_with_extra_columns_not_paired(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A SELECT whose columns are NOT a subset of the fields is not paired."""
        module = tmp_path / "models.py"
        module.write_text(
            "from dataclasses import dataclass\n\n"
            'CARD_SQL = "SELECT id, label, archived FROM cards"\n\n\n'
            "@dataclass(frozen=True, slots=True)\n"
            "class Card:\n"
            "    id: int\n"
            "    label: str\n",  # no 'archived' field -> SELECT not a subset
            encoding="utf-8",
        )

        run_shapes_codegen(_ingest_args(str(module)))

        out = capsys.readouterr().out
        assert "No unannotated dataclass/SELECT pairs found." in out


# ---------------------------------------------------------------------------
# Audit (--audit) — reuses the L2 registry-drift logic
# ---------------------------------------------------------------------------


@shape("SELECT id, title FROM boards WHERE id = :id")
@dataclass(frozen=True, slots=True)
class _CodegenBoardDetail:
    id: int
    title: str


def _register_known_shape() -> None:
    """Ensure a known Shape name is in the registry for the audit tests."""
    register_shape("CodegenBoardDetail", _CodegenBoardDetail)


def _fake_app(surface_contracts: dict[str, str]) -> SimpleNamespace:
    """A minimal app shape exposing ``_mutable_state.contract_check_data``."""
    return SimpleNamespace(
        _mutable_state=SimpleNamespace(contract_check_data={"surface_contracts": surface_contracts})
    )


class TestShapesCodegenAudit:
    def test_audit_reports_drift_and_exits_nonzero(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A surface name with no backing Shape is reported; exit code is non-zero."""
        _register_known_shape()
        app = _fake_app({"board-page": "CodegenBoardDetial"})  # typo -> drift
        monkeypatch.setattr("chirp.cli._resolve.resolve_app", lambda _import: app)

        with pytest.raises(SystemExit) as exc_info:
            run_shapes_codegen(_audit_args("app:app"))

        assert exc_info.value.code != 0
        out = capsys.readouterr().out
        assert "CodegenBoardDetial" in out
        # The reused L2 logic offers the closest-match suggestion.
        assert "CodegenBoardDetail" in out

    def test_audit_clean_registry_exits_zero(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A surface name that resolves to a registered Shape exits 0."""
        _register_known_shape()
        app = _fake_app({"board-page": "CodegenBoardDetail"})  # exists
        monkeypatch.setattr("chirp.cli._resolve.resolve_app", lambda _import: app)

        with pytest.raises(SystemExit) as exc_info:
            run_shapes_codegen(_audit_args("app:app"))

        assert exc_info.value.code == 0
        assert "no Shape drift" in capsys.readouterr().out

    def test_audit_no_surface_contracts_exits_zero(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """An app with no surface_contracts registered has nothing to audit -> 0."""
        app = _fake_app({})
        monkeypatch.setattr("chirp.cli._resolve.resolve_app", lambda _import: app)

        with pytest.raises(SystemExit) as exc_info:
            run_shapes_codegen(_audit_args("app:app"))

        assert exc_info.value.code == 0
        assert "nothing to audit" in capsys.readouterr().out

    def test_audit_unresolvable_app_exits_nonzero(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A failing app import is a clear error with a non-zero exit."""

        def _boom(_import: str):
            raise ModuleNotFoundError("no module named 'nope'")

        monkeypatch.setattr("chirp.cli._resolve.resolve_app", _boom)

        with pytest.raises(SystemExit) as exc_info:
            run_shapes_codegen(_audit_args("nope:app"))

        assert exc_info.value.code != 0
        assert "Error:" in capsys.readouterr().err
