"""Focused tests for steward projection and verification."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).parents[2]
PROJECTOR = PROJECT / ".stewards" / "project.py"
VERIFIER = PROJECT / ".stewards" / "verify.py"


def _run(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_repository_steward_network_is_current_and_covered() -> None:
    projected = _run(PROJECTOR, "--check")
    verified = _run(VERIFIER, "--coverage")

    assert projected.returncode == 0, projected.stdout + projected.stderr
    assert verified.returncode == 0, verified.stdout + verified.stderr


def test_projector_detects_stale_map(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.toml"
    manifest.write_text(
        """
network = "fixture"
[[steward]]
id = "root"
path = "AGENTS.md"
point_of_view = "fixture"
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text("stale\n", encoding="utf-8")

    result = _run(PROJECTOR, "--repo", str(tmp_path), "--manifest", str(manifest), "--check")

    assert result.returncode == 1
    assert "STALE maps" in result.stdout


def test_generated_root_exposes_commands_without_maintenance_context() -> None:
    root_map = (PROJECT / "AGENTS.md").read_text(encoding="utf-8")

    assert "Do not open `.stewards/PROTOCOL.md`" in root_map
    assert "read the root map before repository discovery" in root_map
    assert "Before reading or searching content beneath a path" in root_map
    assert "Search progressively" in root_map
    assert "bounded static traversal" in root_map
    assert (
        "Do not take, implement, close, or batch-plan issues labeled `good first issue`" in root_map
    )
    assert "scripts/backlog.py next" in root_map
    assert "uv run ruff check ." in root_map
    assert "uv run pytest tests/test_lazy_imports.py tests/test_public_api_docs.py -q" in root_map


def test_verifier_rejects_rotted_evidence_anchor(tmp_path: Path) -> None:
    evidence = tmp_path / "contract.py"
    evidence.write_text("class CurrentContract:\n    pass\n", encoding="utf-8")
    manifest = tmp_path / "manifest.toml"
    manifest.write_text(
        """
[[steward]]
id = "root"
path = "AGENTS.md"

[[invariant]]
id = "contract"
steward = "root"
statement = "The contract exists."
severity = "P0"
verification = "manual"
evidence_file = "contract.py"
anchor = "MissingContract"
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text("fixture\n", encoding="utf-8")

    result = _run(VERIFIER, "--repo", str(tmp_path), "--manifest", str(manifest))

    assert result.returncode == 1
    assert "missing anchor" in result.stdout


def test_verifier_rejects_false_machine_backing(tmp_path: Path) -> None:
    proof = tmp_path / "test_contract.py"
    proof.write_text("def test_other():\n    pass\n", encoding="utf-8")
    manifest = tmp_path / "manifest.toml"
    manifest.write_text(
        """
[check.contract]
invoke = "pytest test_contract.py"
location = "test_contract.py"
proof_contains = "test_required_contract"

[[steward]]
id = "root"
path = "AGENTS.md"

[[invariant]]
id = "machine-contract"
steward = "root"
statement = "The focused check proves this contract."
severity = "P0"
verification = "machine"
enforced_by = "contract"
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text("fixture\n", encoding="utf-8")

    result = _run(VERIFIER, "--repo", str(tmp_path), "--manifest", str(manifest))

    assert result.returncode == 1
    assert "proof text not found" in result.stdout


def test_verifier_rejects_rotted_command_path(tmp_path: Path) -> None:
    proof = tmp_path / "test_contract.py"
    proof.write_text("def test_contract():\n    pass\n", encoding="utf-8")
    manifest = tmp_path / "manifest.toml"
    manifest.write_text(
        """
[check.contract]
invoke = "pytest tests/test_missing.py"
location = "test_contract.py"

[[steward]]
id = "root"
path = "AGENTS.md"
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text("fixture\n", encoding="utf-8")

    result = _run(VERIFIER, "--repo", str(tmp_path), "--manifest", str(manifest))

    assert result.returncode == 1
    assert "command path does not exist" in result.stdout
